Please change the code in ReceivingTask.java:
	detected[i].prob = (float)(ByteBuffer.wrap(tmp).order(ByteOrder.LITTLE_ENDIAN).getFloat());
to
	detected[i].prob = (float)(ByteBuffer.wrap(tmp).order(ByteOrder.LITTLE_ENDIAN).getInt());


When we want show more results on SurfaceView, please increase the Conatants.REG_SIZE (client) and ServerUDP.REG_SIZE (server)

For better plot bundle boxes, maybe you need rewrite onDraw() method. 
The resolution of my phone is 2227*1080. In MainActivity class, I rewrite onDraw() method as follows:

		@Override
        protected void onDraw(final Canvas canvas) {
            super.onDraw(canvas);
            if(detecteds != null) {
                for (Detected detected : detecteds) {
                    float height_adjust = 8.3f;
                    canvas.drawRect((detected.left)*7-5, (detected.top)*height_adjust-50,
                            (detected.right)*7, (detected.top)*height_adjust, paintBackground);
                    canvas.drawText(detected.name +  " " + detected.prob,
                            (detected.left)*7, (detected.top)*height_adjust-10, paintWord);
                    canvas.drawRect((detected.left)*7, (detected.top)*height_adjust,
                            (detected.right)*7, (detected.bot)*height_adjust, paintLine);
                }
            }
        }

requirements:
pytorch>=1.7
others requirements in requirements.txt
requirements.txt is the same with yolov5 (https://github.com/ultralytics/yolov5)