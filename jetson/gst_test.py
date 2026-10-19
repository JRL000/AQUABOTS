import gi, numpy as np
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

pipeline = Gst.parse_launch(
    "nvarguscamerasrc ! "
    "video/x-raw(memory:NVMM), width=1280, height=720, framerate=60/1 ! "
    "nvvidconv flip-method=2 ! "
    "video/x-raw, format=BGRx ! "
    "videoconvert ! video/x-raw, format=BGR ! "
    "appsink name=sink max-buffers=1 drop=true sync=false"
)

sink = pipeline.get_by_name('sink')
pipeline.set_state(Gst.State.PLAYING)

import time; time.sleep(3)

for i in range(5):
    sample = sink.emit('pull-sample')
    if sample:
        buf = sample.get_buffer()
        success, info = buf.map(Gst.MapFlags.READ)
        if success:
            frame = np.frombuffer(info.data, dtype=np.uint8).reshape(720, 1280, 3)
            print(f'Frame {i}: shape={frame.shape} mean={frame.mean():.1f}')
            buf.unmap(info)
        else:
            print(f'Frame {i}: buf.map failed')
    else:
        print(f'Frame {i}: no sample')

pipeline.set_state(Gst.State.NULL)
