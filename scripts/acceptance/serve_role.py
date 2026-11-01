"""Test-only authenticated/audited HTTP transport around the public MCP server."""
import argparse,json,time
from pathlib import Path
import uvicorn
from gsm.application import Application
from gsm.mcp.server import create_server

class AuditAuth:
    def __init__(self,app,token,log,role):self.app=app;self.token=token;self.log=log;self.role=role
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        if headers.get(b'authorization',b'').decode()!='Bearer '+self.token:
            await send({'type':'http.response.start','status':401,'headers':[(b'content-type',b'application/json')]})
            return await send({'type':'http.response.body','body':b'{"error":"unauthorized"}'})
        request=[];response=[]
        async def audited_receive():
            message=await receive()
            if message['type']=='http.request':request.append(message.get('body',b''))
            return message
        async def audited_send(message):
            if message['type']=='http.response.body':response.append(message.get('body',b''))
            await send(message)
        try:await self.app(scope,audited_receive,audited_send)
        finally:
            def decoded(chunks):
                raw=b''.join(chunks).decode(errors='replace')
                try:return json.loads(raw)
                except ValueError:return raw
            with self.log.open('a') as f:f.write(json.dumps({'time':time.time(),'role':self.role,'method':scope['method'],'request':decoded(request),'response':decoded(response)},ensure_ascii=False)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--credentials',required=True);p.add_argument('--token-file',required=True);p.add_argument('--log',required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args()
    app=Application(a.credentials);server=create_server(app)
    server.settings.stateless_http=True;server.settings.json_response=True
    asgi=server.streamable_http_app()
    uvicorn.run(AuditAuth(asgi,Path(a.token_file).read_text().strip(),Path(a.log),app.principal.role),host='127.0.0.1',port=a.port,log_level='warning')
if __name__=='__main__':main()
