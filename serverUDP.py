import argparse,socket
from datetime import datetime
import numpy as np
import cv2
import torch
from PIL import Image
import pandas as pd
import threading
import sqlite3
import time

MAX_BYTES = 65536
ip = "0.0.0.0"
port = 9898
REG_SIZE = 2048
db_name = "yolov5detection.db"
save_results_pic = False # save recognized pictures with buddled boxes, or not
save_results_sql = True # save recognized results, such as time using for recognizing, to sqlite3, or not
threshold = 0.5
img_height = 274

def bytes_to_int(inputbytes:bytes): 
    """
    tansfer python bytes to unit8
    """
    length = len(inputbytes)
    int_num = []
    for i in range(length):
        int_num.append(inputbytes[i])
    return int_num

def get_frmid(inputbytes:bytes):
    """
    get framID from python bytes
    """
    return int.from_bytes(inputbytes, byteorder='little', signed=True)

def get_datatype(inputbytes:bytes):
    """
    get datetype from python bytes
    """
    return int.from_bytes(inputbytes, byteorder='little', signed=True)

def get_datasize(inputbytes:bytes):
    """
    get picture's size from python bytes
    """
    return int.from_bytes(inputbytes, byteorder='little', signed=True)

def get_senddata(frmid,results):
    """
    prepare UDP send_data from results gotten from yolov5

    https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_sql.html
    https://blog.csdn.net/weixin_43585712/article/details/98446612
    """
    buffer_temp = results.pandas().xyxy[0]

    total_num_detected = buffer_temp.shape[0]

    bytes_fuffer = bytearray([0]*REG_SIZE)

    bytes_fuffer[0:4] = frmid.to_bytes(4,'little') # bytes中的元素是不能修改的

    total_num_for_send = 0
    
    for i in range(total_num_detected):
        if buffer_temp.iloc[i].loc['confidence'] >= threshold:
            # only send results whois prop bigger than 0.5

            total_num_for_send += 1
            bytes_fuffer[12+i*100:16+i*100] = int(100*buffer_temp.iloc[i].loc['confidence']).to_bytes(4,'little') 
            # confidence
            bytes_fuffer[16+i*100:20+i*100] = int(buffer_temp.iloc[i].loc['xmin']).to_bytes(4,'little')
            # left
            bytes_fuffer[20+i*100:24+i*100] = int(buffer_temp.iloc[i].loc['xmax']).to_bytes(4,'little')
            # right
            bytes_fuffer[24+i*100:28+i*100] = int(buffer_temp.iloc[i].loc['ymin']).to_bytes(4,'little')
            # top
            bytes_fuffer[28+i*100:32+i*100] = int(buffer_temp.iloc[i].loc['ymax']).to_bytes(4,'little')
            # bot

            bytes_name = (buffer_temp.iloc[i].loc['name']+'.').encode("ascii")
            # add '.' as End Of Name

            name_len = len(bytes_name)
            bytes_fuffer[32+i*100:name_len+32+i*100] = bytes_name

    bytes_fuffer[8:12] = total_num_for_send.to_bytes(4,'little')
    return bytes(bytes_fuffer)

def get_senddata_noimage(frmid):
    """
    before 6th frame, there is no picture data
    """
    total_num = 0

    bytes_fuffer = bytearray([0]*REG_SIZE)

    bytes_fuffer[0:4] = frmid.to_bytes(4,'little')
    bytes_fuffer[8:12] = total_num.to_bytes(4,'little')
    return bytes(bytes_fuffer)

class send_thread(threading.Thread):
    """
    server's sending process, is a new thread
    """
    def __init__(self, threadID, name,frmid, sock,ip,results):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.results = results
        self.ip = ip
        self.frmid = frmid
        self.sock = sock
    def run(self):
        senddata = get_senddata(self.frmid,self.results)
        self.sock.sendto(senddata,self.ip)
        if save_results_pic == True:
            self.results.save()
        

class sql_thread(threading.Thread):
    def __init__(self,client_IP,client_port,frmid,datasize,datatype,request_time,result_time,detect_result):
        threading.Thread.__init__(self)
        self.client_IP = client_IP
        self.client_port = client_port
        self.frmid = frmid
        self.datasize = datasize
        self.datatype = datatype
        self.request_time = request_time
        self.result_time = result_time
        self.detect_result = detect_result

    def run(self):
        request_str = create_request_entry(self.client_IP,self.client_port,self.frmid,self.datasize,self.datatype,self.request_time)
        result_str = create_result_entry(self.client_IP,self.client_port,self.frmid,self.datasize,self.datatype,self.result_time,self.detect_result)
        db_yolov5detection = sqlite3.connect(db_name)
        cursor = db_yolov5detection.cursor()
        cursor.execute(result_str)
        cursor.execute(request_str)
        cursor.close()
        db_yolov5detection.close()

class sql_thread2(threading.Thread):
    """
    use a new thread to recode sqlite3
    """
    def __init__(self,cursor,client_IP,client_port,frmid,datasize,datatype,request_time,result_time,detect_result):
        threading.Thread.__init__(self)
        self.cursor = cursor
        self.client_IP = client_IP
        self.client_port = client_port
        self.frmid = frmid
        self.datasize = datasize
        self.datatype = datatype
        self.request_time = request_time
        self.result_time = result_time
        self.detect_result = detect_result

    def run(self):
        request_str = create_request_entry(self.client_IP,self.client_port,self.frmid,self.datasize,self.datatype,self.request_time)
        result_str = create_result_entry(self.client_IP,self.client_port,self.frmid,self.datasize,self.datatype,self.result_time,self.detect_result)
        lock.acquire()
        self.cursor.execute(result_str)
        self.cursor.execute(request_str)
        lock.release()

class sql_request_thread(threading.Thread):
    def __init__(self,cursor,client_IP,client_port,frmid,datasize,datatype,request_time):
        threading.Thread.__init__(self)
        self.cursor = cursor
        self.client_IP = client_IP
        self.client_port = client_port
        self.frmid = frmid
        self.datasize = datasize
        self.datatype = datatype
        self.request_time = request_time

    def run(self):
        request_str = create_request_entry(self.client_IP,self.client_port,self.frmid,self.datasize,self.datatype,self.request_time)
        self.cursor.execute(request_str)

class sql_result_thread(threading.Thread):
    def __init__(self,cursor,client_IP,client_port,frmid,datasize,datatype,result_time,detect_result):
        threading.Thread.__init__(self)
        self.cursor = cursor
        self.client_IP = client_IP
        self.client_port = client_port
        self.frmid = frmid
        self.datasize = datasize
        self.datatype = datatype
        self.request_time = request_time
        self.result_time = result_time
        self.detect_result = detect_result

    def run(self):
        result_str = create_result_entry(self.client_IP,self.client_port,self.frmid,self.datasize,self.datatype,self.result_time,self.detect_result)
        self.cursor.execute(result_str)

def create_request_table():
    create_str = "create table request_table (client_IP varchar(20), client_port INTEGER, framID INTEGER, datasize INTEGER, datatype INTEGER, request_time INTEGER)"
    return create_str
def create_request_entry(client_IP,client_port,framID,datasize,datatype,request_time):
    request_str = '''insert into request_table (client_IP,client_port,framID,datasize,datatype,request_time) values (%s,%d,%d,%d,%d,%d)''' % (client_IP, client_port, framID, datasize, datatype, request_time)
    return request_str

def create_result_table():
    create_str = "create table result_table (client_IP varchar(25), client_port INTEGER, framID INTEGER, datasize INTEGER, datatype INTEGER, result_time INTEGER, detect_result, TEXT)"
    return create_str

def create_result_entry(client_IP,client_port,framID,datasize,datatype,result_time,detect_result):
    result_str = '''insert into result_table (client_IP, client_port, framID, datasize, datatype, result_time, detect_result) values (%s, %d, %d, %d, %d, %d, %s)''' % (client_IP,client_port,framID,datasize,datatype,result_time,detect_result)
    return result_str


if __name__ == "__main__":

    """
    get yolov5 model from URL:

    then create a database named "yolov5detection.db", to recode requestion and results from yolov5

    use a UDP socket to receive and send data

    use python bytes class to receive data sended by java byte[]

    use a new thread to send results,if you want to recode the results use a database, please set "save_results_sql = True".

    if you want save recognized pictures with buddled boxes, please set "save_results_pic = True", the results will be saved at ./run/hub/
    

    """

    model = torch.hub.load('ultralytics/yolov5', 'yolov5x').cuda()

    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    #绑定IP地址和和端口

    db_yolov5detection = sqlite3.connect(db_name,check_same_thread = False)
    cursor = db_yolov5detection.cursor()

    try:
        cursor.execute(create_result_table())
    except:
        print("Create table failed")

    try:
        cursor.execute(create_request_table())
    except:
        print("Create table failed")

    sock.bind((ip,port))
    

    print("Listening at {}".format(sock.getsockname()))

    lock = threading.Lock()

    while True:
        data,address = sock.recvfrom(MAX_BYTES)
        request_time = time.time()
        client_IP = "\'"+address[0]+"\'"
        client_port = address[1]
        frmid = get_frmid(data[0:4])
        datatype = get_datatype(data[4:8])
        datasize = get_datasize(data[8:12])

        # sql_request = sql_request_thread(cursor,client_IP,client_port,frmid,datasize,datatype,request_time)
        # sql_request.start()

        if frmid<=5:
            "before 6th frame, there is no picture data"
            senddata = get_senddata_noimage(frmid)
            sock.sendto(senddata,address)
            detect_result = "'\ \'"
            result_time = time.time() - request_time

        if frmid > 5:
            pic_of_byte = np.frombuffer(data[12:12+datasize],np.uint8)
            img = np.flip(np.transpose(cv2.imdecode(pic_of_byte,cv2.IMREAD_UNCHANGED)),1)
            # I find the picture from android, need to transpose and flip operation(because the resolution of my phone is vertical )
            # if you device's resolution is horizontal, maybe, there is no need to transpose and flip.

            # cv2.imshow("test",img)
            # cv2.waitKey()
            with torch.no_grad():
                results = model(img, size=img_height)
            result_time = time.time() - request_time # time used by yolov5 model

            # results.print()  
            # results.xyxy[0]  # img1 predictions (tensor)
            # results.pandas().xyxy[0]  # img1 predictions (pandas)
            # results.save()
            # senddata = get_senddata(frmid,results)

            T1 = send_thread(1,"1",frmid, sock,address,results)
            T1.start()
            detect_result = "\'"+ str(results.pandas().xyxy[0]) +"\'"

        if save_results_sql == True:
            sql = sql_thread2(cursor,client_IP,client_port,frmid,datasize,datatype,request_time,result_time,detect_result)
            sql.start()
            if frmid % 150 == 0:
                db_yolov5detection.commit()
  
        # sql_result = sql_result_thread(cursor,client_IP,client_port,frmid,datasize,datatype,result_time,detect_result)
        # sql_result.start()
        # sql = sql_thread2(cursor,client_IP,client_port,frmid,datasize,datatype,request_time,result_time,detect_result)
        # sql.start()

        # request_str = create_request_entry(client_IP,client_port,frmid,datasize,datatype,request_time)
        # result_str = create_result_entry(client_IP,client_port,frmid,datasize,datatype,result_time,detect_result)
        # cursor.execute(request_str)
        # cursor.execute(result_str)

    