"""Trusted verifier oracleı; producer workspace'ine yazılabilir bağlanmaz."""
import importlib.util,json,sys
from pathlib import Path

CASES=[('plain','Görev','Görev',None),('trim','  Görev  ','Görev',None),
 ('collapse','Yeni   görev','Yeni görev',None),('mixed',' \tYeni\n\tgörev  ','Yeni görev',None),
 ('unicode','  İŞ   ıslahı  ','İŞ ıslahı',None),('nbsp','a\u00a0\u00a0b','a b',None),
 ('empty','',None,ValueError),('only_space',' \t\n',None,ValueError),
 ('wrong_type',None,None,TypeError),('numeric',7,None,TypeError),
 ('boundary','a'*120,'a'*120,None),('too_long','a'*121,None,ValueError),
 ('normalized_length','a'+' '*121+'b','a b',None)]

def verify(path):
    spec=importlib.util.spec_from_file_location('candidate_title',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    results=[]
    for ident,value,expected,error in CASES:
        try:
            got=module.normalize_title(value);passed=error is None and got==expected
        except Exception as exc:passed=error is not None and type(exc) is error
        results.append({'id':ident,'result':'PASS' if passed else 'FAIL'})
    return results

if __name__=='__main__':
    results=verify(Path(sys.argv[1]));print(json.dumps({'checks':results,'passed':sum(x['result']=='PASS' for x in results),'total':len(results)}))
    raise SystemExit(0 if all(x['result']=='PASS' for x in results) else 1)
