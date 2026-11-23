#!/usr/bin/env python
"""Offline tests for tools/reembed.py (fake embedder, temp database, nothing real touched).
Run from the winter-assistant folder:   python tests/test_reembed.py
"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd, lancedb
from tools.reembed import reembed_table, pooling_mode, texts_for
from storage.evidence_store import evidence_schema, TABLE
from storage.lancedb_storage import _schema
class Emb:
    dim=8
    def encode_docs(self, texts, batch_size=64):
        v=np.array([[len(t)%7+1, t.count("e")+1, 1,2,3,4,5,6] for t in texts],dtype=np.float32)
        return v/np.linalg.norm(v,axis=1,keepdims=True)
db=lancedb.connect(tempfile.mkdtemp())
ev=pd.DataFrame({"id":[0,1],"text":["i eat burritos","viewer1 says hi"],"author":["a","b"],"is_owner":[True,False],
  "source":"twitch","date":["2025-01-01"]*2,"ts":["2025-01-01 10:00:00"]*2,"channel":"c","vector":[[0.0]*8]*2})
db.create_table(TABLE,data=ev,schema=evidence_schema(8))
cv=pd.DataFrame({"conversation_id":["x"],"title":["t"],"timestamp":[1.0],"datetime":["d"],"session":[1],"project":[""],
  "turn_number":[0],"user":["hi"],"assistant":["yo"],"elapsed":[0.1],"vector":[[0.0]*8]})
db.create_table("conversations",data=cv,schema=_schema(8))
n,_=reembed_table(db,TABLE,Emb(),dry_run=True)
assert np.allclose(np.stack(db.open_table(TABLE).to_pandas()["vector"]),0), "dry run wrote!"
reembed_table(db,TABLE,Emb()); reembed_table(db,"conversations",Emb())
e=db.open_table(TABLE).to_pandas(); c=db.open_table("conversations").to_pandas()
assert list(e["text"])==["i eat burritos","viewer1 says hi"] and list(e["is_owner"])==[True,False] and e["ts"][0]=="2025-01-01 10:00:00"
assert np.allclose(np.stack(e["vector"]), Emb().encode_docs(list(e["text"])))
assert np.allclose(np.stack(c["vector"]), Emb().encode_docs(["user: hi | assistant: yo"]))
assert db.open_table(TABLE).schema == evidence_schema(8)
reembed_table(db,"missing",Emb())
class P: pass
class Pooling:
    pooling_mode_lasttoken=True; pooling_mode_mean_tokens=False
class Fake: model=[object(), Pooling()]
assert pooling_mode(Fake())=="lasttoken"
Pooling.pooling_mode_lasttoken=False; Pooling.pooling_mode_mean_tokens=True
assert pooling_mode(Fake())=="mean"
print("\n✅ reembed: dry run writes nothing, only vectors change, schema kept, pooling detected")
