# pyportal-zabbix-problems

This code sets up your pyPortal to download current issues from your Zabbix server.
The buttons as I have them wired advance the host list (blue button), or refresh the issue data.

![demo gif](/demo/animation.gif)

## Create a secrets.py file

This code expects the following in your secrets.py file:

```
secrets = {
'ssid' : 'SSID', # Keep the two '' quotes around the name
'password' : 'PASSWORD', # Keep the two '' quotes around password
'timezone' : "America/Chicago", # http://worldtimeapi.org/timezones
'api_url' : "http://ZABBIX_SERVER/api_jsonrpc.php",
'auth_key' : "ZABBIX_AUTH_KEY"
}
```

## The following circuitpython libraries are needed

- adafruit_bitmap_font
- adafruit_display_text
- adafruit_esp32spi
- adafruit_fakerequests.mpy
- adafruit_io
- adafruit_portalbase
- adafruit_pyportal
- adafruit_requests.mpy
- adafruit_touchscreen.mpy
- neopixel.mpy
