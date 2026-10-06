"""Generate mobile assets from the desktop export, retaining its exact scene bounds."""
import json,re,base64
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent
s=(root/'data.js').read_text()
t=json.loads(re.search(r'const TERRAIN = (.*?);',s).group(1))
a=np.frombuffer(base64.b64decode(t['elevationBase64']),dtype='<i2').reshape(t['rows'],t['cols']).astype(np.float32)
w=513;h=round((t['rows']-1)/(t['cols']-1)*(w-1))+1
# Endpoint-aligned bilinear sample preserves the existing mesh mapping.
x=np.linspace(0,a.shape[1]-1,w);y=np.linspace(0,a.shape[0]-1,h);x0=x.astype(int);y0=y.astype(int);x1=np.minimum(x0+1,a.shape[1]-1);y1=np.minimum(y0+1,a.shape[0]-1);fx=x-x0;fy=(y-y0)[:,None]
b=(a[y0[:,None],x0]*(1-fx)+a[y0[:,None],x1]*fx)*(1-fy)+(a[y1[:,None],x0]*(1-fx)+a[y1[:,None],x1]*fx)*fy
mobile=dict(t,cols=w,rows=h,elevationBase64=base64.b64encode(np.rint(b).astype('<i2').tobytes()).decode())
(root/'data-mobile.js').write_text('const TERRAIN = '+json.dumps(mobile,separators=(',',':'))+';\n')
im=Image.open(root/'texture.jpg');im.thumbnail((2048,2048),Image.Resampling.LANCZOS);im.save(root/'texture-mobile.jpg',quality=90,optimize=True)
(root/'texture-mobile.js').write_text('window.TEXTURE_DATA_URI = "data:image/jpeg;base64,'+base64.b64encode((root/'texture-mobile.jpg').read_bytes()).decode()+'";\n')
