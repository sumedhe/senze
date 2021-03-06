#!/usr/bin/env python

###############################################################################
##
##  My Sensor UDP Client v1.0
##  @Copyright 2014 MySensors Research Project
##  SCoRe Lab (www.scorelab.org)
##  University of Colombo School of Computing
##
##  Licensed under the Apache License, Version 2.0 (the "License");
##  you may not use this file except in compliance with the License.
##  You may obtain a copy of the License at
##
##      http://www.apache.org/licenses/LICENSE-2.0
##
##  Unless required by applicable law or agreed to in writing, software
##  distributed under the License is distributed on an "AS IS" BASIS,
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
##  See the License for the specific language governing permissions and
##  limitations under the License.
##
###############################################################################


from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
import datetime

import socket
import time
import sys
import thread
import os.path
lib_path = os.path.abspath('../utils')
sys.path.append(lib_path)
from myParser import *
from myCrypto import *
from myDriver import *
from myCamDriver import *
import re
import hashlib
#from PIL import Image

host='udp.mysensors.info'
#host='localhost'
port=9090
state="INITIAL"
device=""
server="mysensors"
serverPubKey=""
aesKeys={}

class mySensorDatagramProtocol(DatagramProtocol):
  
    def __init__(self, host,port,reactor):
        self.ip= socket.gethostbyname(host)
        self.port = port
        #self._reactor=reactor
        #self.ip=reactor.resolve(host)

    def sendPing(self):
       senze="DATA #msg PING"
       self.sendDatagram(senze)
       reactor.callLater(600,self.sendPing)

    def readSenze(self):
        while True:
             response=raw_input("Enter your Senze:")
             self.sendDatagram(response)


    def startProtocol(self):
        self.transport.connect(self.ip,self.port)
        if state=='INITIAL':
           #If system is at the initial state, it will send the device creation Senze
           self.register()
        else:
           #thread.start_new_thread(self.showPhoto,("p1.jpg",))
           reactor.callLater(1,self.sendPing)
           if os.path.isfile('SENZES'):
              #The Senzes will be read form the SENZE file
              f=open("SENZES","r")
              lines = f.readlines()
              t=0
              for line in lines:
                  if not line.startswith("#"):
                     senze=line.rstrip("\n")
                     t+=2
                     reactor.callLater(t,self.sendDatagram,senze=senze)
           #thread.start_new_thread(self.readSenze,()) 
           #response=raw_input("Enter your Senze:")
           #self.sendDatagram(response)

    def stopProtocol(self):
        #on disconnect
        #self._reactor.listenUDP(0, self)
        print "STOP **************"

    def register(self):
        global server
        cry=myCrypto(name=device) 
        senze ='SHARE #pubkey %s @%s' %(pubkey,server)
        senze=cry.signSENZE(senze)
        self.transport.write(senze)
        
    def sendDatagram(self,senze):
        global server
        cry=myCrypto(name=device)
        senze=cry.signSENZE(senze)
        print senze
        self.transport.write(senze)
    

    #Senze response should be built as follows by calling the functions in the driver class
    def sendDataSenze(self,sensors,data,recipient):
       global device
       global aesKeys

       response='DATA'
       driver=myDriver()
       cry=myCrypto(device)         

       for sensor in sensors:
           #If temperature is requested
           if "tp" == sensor:
              response ='%s #tp %s' %(response,driver.readTp())

           #If AES key is requested
	   if "key" == sensor:
             aeskey=""         
             #Generate AES Key
             if cry.generateAES(driver.readTime()):
                aeskey=cry.key
		#Save AES key
                aesKeys[recipient]=aeskey
                #AES key is encrypted by the recipient public key
                rep=myCrypto(recipient)
                encKey=rep.encryptRSA(b64encode(aeskey))
             response ='%s #key %s' %(response,encKey)

           #If photo is requested
           elif "photo" == sensor:
              cam=myCamDriver()
              cam.takePhoto()
              photo=cam.readPhotob64()
              response ='%s #photo %s' %(response,photo)

           #If time is requested
           elif "time" == sensor:
              response ='%s #time %s' %(response,driver.readTime())

           #If gps is requested 
           elif "gps" == sensor:
              #if AES key is available, gps data will be encrypted
              gpsData='%s' %(driver.readGPS())
              if recipient in aesKeys:
                 rep=myCrypto(recipient)
                 rep.key=aesKeys[recipient]
                 gpsData=rep.encrypt(gpsData)
              response ='%s #gps %s' %(response,gpsData)

           #If gpio is requested 
           elif "gpio" in sensor:
              m=re.search(r'\d+$',sensor)
              pinnumber=int(m.group())
              print pinnumber
              response ='%s #gpio%s %s' %(response,pinnumber,driver.readGPIO(port=pinnumber))
           else:
              response ='%s #%s NULL' %(response,sensor)
       
       response="%s @%s" %(response,recipient)
       senze=cry.signSENZE(response)
       print senze
       self.transport.write(senze)
        
       #Data can be encrypted as follows
       #cry=myCrypto(recipient)
       #enc=cry.encryptRSA(response)
       #response="DATA #cipher %s @%s" %(enc,recipient)
       

    #Handle the GPIO ports by calling the functions in the driver class
    def handlePUTSenze(self,sensors,data,recipient):
       global device
       response='DATA'
       driver=myDriver()
       cry=myCrypto(device)
       for sensor in sensors:
          #If GPIO operation is requested
          if "gpio" in sensor:
              pinnumber=0
              #search for gpio pin number
              m=re.search(r'\d+$',sensor)
              if m :
                 pinnumber=int(m.group())
            
              if pinnumber>0 and pinnumber<=16:
                 if data[sensor]=="ON": ans=driver.handleON(port=pinnumber)
                 else: ans=driver.handleOFF(port=pinnumber)
                 #response='%s #gpio%s %s' %(response,pinnumber,ans)
                 response='%s #msg %s' %(response,ans)

              else: 
                 response='%s #gpio%d UnKnown' %(response,pinnumber)
          elif sensor!="time":
              response='%s #%s UnKnown' %(response,sensor)
          
       response="%s @%s" %(response,recipient)
       senze=cry.signSENZE(response)
       self.transport.write(senze)


    def handleServerResponse(self,senze):
        sender=senze.getSender()
        data=senze.getData()
        sensors=senze.getSensors()
        cmd=senze.getCmd()
 
        if cmd=="DATA":
           if 'msg' in sensors and 'UserRemoved' in data['msg']:
              cry=myCrypto(device)
              try:
                 os.remove(".devicename")
                 os.remove(cry.pubKeyLoc)
                 os.remove(cry.privKeyLoc)
                 print "Device was successfully removed"
              except OSError:
                 print "Cannot remove user configuration files"
              reactor.stop()

           elif 'pubkey' in sensors and data['pubkey']!="" and 'name' in sensors and data['name']!="":
                 recipient=myCrypto(data['name'])
                 if recipient.saveRSAPubKey(data['pubkey']):
                    print "Public key=> "+data['pubkey']+" Saved."
                 else:
                    print "Error: Saving the public key."

    def handleDeviceResponse(self,senze):
        global device
        global aesKeys
        sender=senze.getSender()
        data=senze.getData()
        sensors=senze.getSensors()
        cmd=senze.getCmd()
 
        if cmd=="DATA":
           for sensor in sensors:
               if sensor in data.keys():
                  print sensor+"=>"+data[sensor]
       
           if 'photo' in sensors:
               #try:
                   cam=myCamDriver()
                   cam.savePhoto(data['photo'],"p1.jpg")
                   #cam.showPhoto("p1.jpg")
                   #self.savePhoto(data['photo'],"p1.jpg")
                   thread.start_new_thread(cam.showPhoto,("p1.jpg",))
               #except:
               #    print "Error: unable to show the photo"
               #cam.savePhoto(data['photo'],"p1.jpg")

           #Received and saved the AES key
           elif 'key' in sensors and data['key']!="":
                #Key need to be decrypted by using the private key
                cry=myCrypto(device)
                dec=cry.decryptRSA(data['key'])
        	aesKeys[sender]=b64decode(dec)
                
           #Decrypt and show the gps data
           elif 'gps' in sensors and data['gps']!="":
                gpsData=data['gps']
                if sender in aesKeys:
                   rep=myCrypto(sender)
                   rep.key=aesKeys[sender]
                   gpsData=rep.decrypt(gpsData)
                print "GPS=>"+gpsData

        elif cmd=="SHARE":
           print "This should be implemented"

        elif cmd=="UNSHAR":
           print "This should be implemented"

        elif cmd=="GET":
           #If GET Senze was received. The device must handle it.
           reactor.callLater(1,self.sendDataSenze,sensors=sensors,data=data,recipient=sender) 
        elif cmd=="PUT":
           reactor.callLater(1,self.handlePUTSenze,sensors=sensors,data=data,recipient=sender)
        else:
           print "Unknown command"


    def datagramReceived(self, datagram, host):
        global device
        print 'Datagram received: ', repr(datagram)
        
        parser=myParser(datagram)
        recipients=parser.getUsers()
        sender=parser.getSender()
        signature=parser.getSignature()
        data=parser.getData()
        sensors=parser.getSensors()
        cmd=parser.getCmd()
       
        validQuery=False  
        cry=myCrypto(device)
        if state=="READY":
           if serverPubkey !="" and sender=="mysensors":
              if cry.verifySENZE(parser,serverPubkey):
                 self.handleServerResponse(parser)
              else:
                 print "SENZE Verification failed"
           else:
              if sender!="":
                 recipient=myCrypto(sender)
                 if os.path.isfile(recipient.pubKeyLoc):
                    pub=recipient.loadRSAPubKey()
                 else:
                    pub=""
                 if pub!="" and cry.verifySENZE(parser,pub):
                    print "SENZE Verified"
                    self.handleDeviceResponse(parser)
                 else:
                    print "SENZE Verification failed"
               
        else:
           if cmd=="DATA":
              if 'msg' in sensors and 'REGISTRATION_DONE' in data['msg']:
                 # Creating the .devicename file and store the device name 
                 # public key of mysensor server  
                 f=open(".devicename",'w')
                 f.write(device+'\n')
                 if 'pubkey' in sensors: 
                     pubkey=data['pubkey']
                     f.write(pubkey+'\n')
                 f.close()
                 print device+ " was created at the server."
                 print "You should execute the program again."
                 print "The system halted!"
                 reactor.stop()

           elif 'msg' in sensors and 'ALREADY_REGISTERED' in data['msg']:
                 print "This user name may be already taken"
                 print "You can try it again with different username"
                 print "The system halted!"
                 reactor.stop()
            
         #self.sendDatagram()

def init():
    #cam=myCamDriver()
    global device
    global pubkey
    global serverPubkey
    global state
    #If .device name is not there, we will read the device name from keyboard
    #else we will get it from .devicename file
    try:
      if not os.path.isfile(".devicename"):
         device=raw_input("Enter the device name: ")
         # Account need to be created at the server
         state='INITIAL'
      else:
         #The device name and server public key will be read form the .devicename file
         f=open(".devicename","r")
         device = f.readline().rstrip("\n")
         serverPubkey=f.readline().rstrip("\n")
         print serverPubkey
         state='READY'
    except:
      print "ERRER: Cannot access the device name file."
      raise SystemExit

    #Here we will generate public and private keys for the device
    #These keys will be used to perform authentication and key exchange
    try:
      cry=myCrypto(name=device)
      #If keys are not available yet
      if not os.path.isfile(cry.pubKeyLoc):
         # Generate or loads an RSA keypair with an exponent of 65537 in PEM format
         # Private key and public key was saved in the .devicenamePriveKey and .devicenamePubKey files
         cry.generateRSA(bits=1024)
      pubkey=cry.loadRSAPubKey()
    except:
        print "ERRER: Cannot genereate private/public keys for the device."
        raise SystemExit
    print pubkey
   
    #Check the network connectivity.
    #check_connectivity(ServerName)

def main():
    global host
    global port
    protocol = mySensorDatagramProtocol(host,port,reactor)
    reactor.listenUDP(0, protocol)
    reactor.run()

if __name__ == '__main__':
    init()
    main()
