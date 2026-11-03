"""Isolated PDFium worker. Only reads a product-authorized immutable PDF blob."""
import io,sys
import pypdfium2 as pdfium

def render(path,page_number):
    document=pdfium.PdfDocument(path)
    try:
        if not 1<=page_number<=len(document):raise ValueError('page range')
        page=document[page_number-1]
        try:
            width,height=page.get_size()
            bitmap=page.render(scale=min(2.0,1800/max(width,height)),limit_image_cache=True)
            try:
                output=io.BytesIO();bitmap.to_pil().save(output,format='PNG');return output.getvalue()
            finally:bitmap.close()
        finally:page.close()
    finally:document.close()
if __name__=='__main__':
    try:sys.stdout.buffer.write(render(sys.argv[1],int(sys.argv[2])))
    except Exception:raise SystemExit(2)
