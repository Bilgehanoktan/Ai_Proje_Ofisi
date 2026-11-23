"""İzinli, supervisor-owned snapshot için gerçek dosya manifesti; sandbox yerine geçmez."""
from pathlib import Path, PurePosixPath
import hashlib, json, os, stat

def _entry(path: Path):
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
        raise ValueError('MANIFEST_LINK_OR_REPARSE_POINT')
    return info

def build_manifest(root: Path, allowed_paths: list[str], *, revision: int, source_digest: str,
                   max_files=128, max_file_bytes=262144, max_total_bytes=2097152) -> dict:
    # Bu kilit alınmış immutable kopya önkoşuludur. Saldırgan eşzamanlı filesystem
    # değişimine karşı portable path kontrolünü race-proof olarak sunmuyoruz.
    if type(revision) is not int or revision<0:raise ValueError('INVALID_REVISION')
    if len(source_digest)!=64 or any(c not in '0123456789abcdef' for c in source_digest):raise ValueError('INVALID_SOURCE_DIGEST')
    if not 0<len(allowed_paths)<=max_files:raise ValueError('MANIFEST_FILE_LIMIT')
    root=Path(os.path.abspath(root))
    for p in [*reversed(root.parents),root]:_entry(p)
    if not root.is_dir():raise ValueError('MANIFEST_ROOT_NOT_DIRECTORY')
    rows=[];total=0;seen=set()
    for name in sorted(allowed_paths):
        rel=PurePosixPath(name)
        if (not rel.parts or rel.is_absolute() or '..' in rel.parts or str(rel)!=name
            or any(c in name for c in '\\:') or any(ord(c)<32 or ord(c)==127 for c in name)):
            raise ValueError('MANIFEST_PATH_OUT_OF_SCOPE')
        if name.casefold() in seen:raise ValueError('MANIFEST_DUPLICATE_PATH')
        seen.add(name.casefold())
        current=root
        for part in rel.parts:
            current=current/part;info=_entry(current)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('MANIFEST_NONREGULAR_OR_HARDLINK')
        if info.st_size>max_file_bytes:raise ValueError('MANIFEST_FILE_TOO_LARGE')
        with current.open('rb') as stream:
            opened=os.fstat(stream.fileno())
            if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('MANIFEST_FILE_CHANGED')
            raw=stream.read(max_file_bytes+1);after=os.fstat(stream.fileno())
        final=_entry(current)
        # Python 3.12 Windows stat/fstat ctime alanları farklı zaman semantiği
        # döndürebilir. Handle/path ortak kontrolünde ctime kullanılmaz;
        # path öncesi/sonrası ctime ayrıca aynı API üzerinden karşılaştırılır.
        signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_mode,s.st_nlink)
        if (signature(info)!=signature(after) or signature(after)!=signature(final)
            or info.st_ctime_ns!=final.st_ctime_ns
            or (os.name!='nt' and info.st_ctime_ns!=after.st_ctime_ns)):
            raise ValueError('MANIFEST_FILE_CHANGED')
        if len(raw)>max_file_bytes:raise ValueError('MANIFEST_FILE_TOO_LARGE')
        total+=len(raw)
        if total>max_total_bytes:raise ValueError('MANIFEST_TOTAL_LIMIT')
        # İçerik/secret ve keyfi LLM özeti manifeste taşınmaz.
        rows.append(dict(relative_path=name,kind='FILE',mode=stat.S_IMODE(info.st_mode),size_bytes=len(raw),content_digest=hashlib.sha256(raw).hexdigest()))
    tree=json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    body=dict(version='workspace-manifest/1',revision=revision,source_digest=source_digest,
              candidate_digest=hashlib.sha256(tree).hexdigest(),files=rows)
    body['manifest_digest']=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    return body
