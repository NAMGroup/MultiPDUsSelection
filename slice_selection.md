## Slice Selection and Switching Mechanism 

A UE-initiated slice selection mechanism was studied and tested on Amarisoft and Ericsson 5G SA Networks using a **Linux Host System**  with a **Quectel RM520N-GL** modem.


Modem Firmware: RM520NGLAAR03A03M4G. 

For communication and modem control AT Commands, QMI protocol and quectel-CM were used. 


### Necessary tools and drivers 

1. Quectel-CM , data call tool provided by the Support of Quectel Forums after request.

2. qmi_wwan_q , provided by the Support of Quectel Forums after request. 

https://forums.quectel.com/



This mechanism relies on the capability of the modem to initiate PDU Session Establishment Requests tied to different Slices. More specifically, it was possible to create PDU profiles with specific parameters, including DNN, S-NSSAI and activate them to connect to the network using the quectel data call tool.


1. Install required packages
```
sudo apt update
sudo apt install libqmi-utils busybox minicom 
```

2. Create a new dir and download Quectel-CM and qmi_wwan_q. 
```
mkdir Quectel 
unzip Quectel_QConnectManager_Linux_V1.6.8.zip
unzip Quectel_Linux_Android_QMI_WWAN_Driver_V1.2.9.zip
```
Inside the folders that were created after unzip:

```
make
```


3. Check if the modem is recognized by Linux kernel as a USB device

```
lsusb
```
Expected output:
```
Bus 002 Device 003: ID 2c7c:0801 Quectel Wireless Solutions Co., Ltd. RM520N-GL
```



4. Find the primary serial device node under /dev/ttyUSB* (usually /dev/ttyUSB2) and access it with minicom:

```
sudo minicom -D /dev/ttyUSBX
```

5. Activate the ECHO mode: 
```
Control + A , then press E
```

The main AT command interface is now open.

6. Set the modem to QMI mode. This is necessary only the **first time** you configure the modem. If it is already configured **skip steps 6 and 7**. 

```
AT+QCFG="usbnet",0 

OK
```

7. Reboot the modem
```
AT+CFUN=1,1
```

8. Allow to establish multiple PDU Connections with the same DNN. It is necessary in order to create PDU Profiles with the same DNN. Only the **first time** you configure the modem. 
```
AT+QCFG="pdp/duplicatechk",1 
```

9. **Create PDU Profiles**
For defining PDU Session Parameters. Each profile is identified by CID number. The following parameters are configured for this implementation:

- PDU_type (IPV4V6,IPV4,IPV6,PPP)
- DNN (internet, ims, default)
- S-NSSAI : The Slice you want to connect to. 

Check the available profiles:
```

AT+CGDCONT?

+CGDCONT: 1,"IPV4V6","default","0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0",0,0,0,0,,,,,,,,,"",,,,0
+CGDCONT: 2,"IPV4V6","ims","0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0",0,0,0,0,,,,,,,,,"",,,,0
+CGDCONT: 3,"IPV4V6","sos","0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0",0,0,0,1,,,,,,,,,"",,,,0
+CGDCONT: 4,"IPV4V6","internet_EMBB00000B","0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0",0,0,0,0,,,,,,,,0,"01.00000B",,,,0
+CGDCONT: 5,"IPV4V6","internet_EMBB00000C","0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0",0,0,0,0,,,,,,,,0,"01.00000C",,,,0

OK
``` 


Add a new profile:
```
AT+CGDCONT=<CID>, <Access_Type>,<DNN>, ,,,,,,,,,,,,,0,<S-NSSAI>,

For example:
AT+CGDCONT=6,"IPV4V6","internet",,,,,,,,,,,,,,0,"01",
```

Notes: 
- You can have only 2 Profiles with the same DNN. 
- Do NOT modify profiles 2 and 3. 
- You can NOT add a S-NSSAI to CID 1.



10. (Optional) Update the default configuration NSSAI stored at the modem to include the new Slices you entered. 

```
AT+C5GNSSAI=<dfl_nssai_len>,<dfl_config_nssai>
```

11. Get updates about Registration Status.
```
AT+C5GREG=2

OK
```


The PDU Profiles are now configured. For establishing a PDU Session with a specific profile quectel-CM is utilised. 


**If qmi_wwan driver is used, only one PDU Session can be activated. You can have multiple PDU Sessions simultaneously with driver qmi_wwan_q.**


Check which driver is used: (Default qmi_wwan)
```
sudo ethtool -i wwan0
```

12. Check if the device node exists. This is the QMI control interface. 
```
ls /dev/cdc-wdm*

Expected output: /dev/cdc-wdm0
```

#### A. Driver qmi_wwan (default)

13. Check if the wwan0 interface is created successfully. This is the network interface for carrying the IP traffic. 

```
ip a 

 wwan0: <POINTOPOINT,MULTICAST,NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000
    link/none

```

14. Activate the PDU Profile of your choice:
```
open terminal in Quectel_QConnectManager_Linux_V1.6.8

sudo ./quectel-CM -n <CID number>
```
For example if you want to activate Profile with CID 5:
sudo ./quectel-CM -n 5 


15. Check if the connection is successful. The wwan0 must obtain an IP. Then test ping and iperf3 
```
4: wwan0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UNKNOWN group default qlen 1000
    link/none
    inet 172.16.222.212/29 scope global wwan0
       valid_lft forever preferred_lft forever
    inet6 fe80::a5a4:7e0c:7865:7e25/64 scope link stable-privacy
       valid_lft forever preferred_lft forever
```


#### B. Driver qmi_wwan_q

13. Unload qmi_wwan driver and load qmi_wwan_q, 
qmap_mode defines the number of active PDU Sessions. Maximum number= 7  

```
sudo modprobe -r qmi_wwan
sudo modprobe usbnet
sudo modprobe cdc_wdm

sudo insmod Quectel/Quectel_Linux_Android_QMI_WWAN_Driver_V1.2.9/qmi_wwan_q.ko 

```


14. Check if the interfaces are created 
```
ip a

6: wwan0: <NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000
    link/ether 46:63:f2:ef:73:a5 brd ff:ff:ff:ff:ff:ff
7: wwan0_1: <NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000
    link/ether 46:63:f2:ef:73:a5 brd ff:ff:ff:ff:ff:ff
8: wwan0_2: <NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000
    link/ether 46:63:f2:ef:73:a5 brd ff:ff:ff:ff:ff:ff
9: wwan0_3: <NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000
    link/ether 46:63:f2:ef:73:a5 brd ff:ff:ff:ff:ff:ff
10: wwan0_4: <NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000
    link/ether 46:63:f2:ef:73:a5 brd ff:ff:ff:ff:ff:ff
```


15. Run qmi proxy 



For the next Steps: 2 PDU Sessions are activated
- CID 4 to wwan0_4 
- CID 5 to wwan0_1

16. Activate the profiles of you choice
```
sudo ./quectel-CM -n <CID> 

For example:
sudo ./quectel-CM -n 4

sudo ./quectel-CM -n 5 

```

17. Check if the interfaces obtained IP addresses.
```

7: wwan0_1: <NOARP,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP group default qlen 1000
    link/ether 46:63:f2:ef:73:a5 brd ff:ff:ff:ff:ff:ff
    inet 172.16.222.214/30 brd 172.16.222.215 scope global dynamic noprefixroute wwan0_1
       valid_lft 6856sec preferred_lft 6856sec
    inet6 fe80::6ef6:6a47:d165:81e0/64 scope link noprefixroute
       valid_lft forever preferred_lft forever

10: wwan0_4: <NOARP,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP group default qlen 1000
    link/ether 46:63:f2:ef:73:a5 brd ff:ff:ff:ff:ff:ff
    inet 172.16.222.212/29 brd 172.16.222.215 scope global dynamic noprefixroute wwan0_4
       valid_lft 6831sec preferred_lft 6831sec
    inet6 fe80::3a38:e33c:d8f6:6d78/64 scope link noprefixroute
       valid_lft forever preferred_lft forever
```

18. Create Routing Tables for every interface in use

```
cat /etc/iproute2/rt_tables

In the end of the file add the new tables. 
101	wwan4
102	wwan1
```

19. Add rules to the tables
```
sudo ip rule add from 172.16.222.212 table wwan4
sudo ip rule add from 172.16.222.214 table wwan1
```

20. Add routes to the interfaces

```
sudo ip route add 172.16.222.212/30 dev wwan0_1 scope link table wwan1
sudo ip route add default via 172.16.222.213 dev wwan0_1 table wwan1


sudo ip route add 172.16.222.208/29 dev wwan0_4 scope link table wwan4
sudo ip route add default via 172.16.222.213 dev wwan0_4 table wwan4
```

30. Test the connections using ping and iperf 
```
For example, for CID 4 connection: 

ping -I wwan0_4 8.8.8.8

iperf3 -c <IP_server> -B 172.16.222.212
```

