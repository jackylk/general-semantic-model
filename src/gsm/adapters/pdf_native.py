"""Local-only helper executed with the parser runtime's Python, not a service."""
import json
import sys


def main():
    from pypdf import PdfReader
    pages=[];characters=0
    for number,page in enumerate(PdfReader(sys.argv[1]).pages,start=1):
        text=page.extract_text(extraction_mode='layout') or ''
        characters+=len(text)
        if characters>2_000_000:raise ValueError('native text limit exceeded')
        pages.append({'page':number,'text':text})
    print(json.dumps({'pages':pages},ensure_ascii=False))


if __name__=='__main__':main()
