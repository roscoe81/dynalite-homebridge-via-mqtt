#!/usr/bin/env python3
#Northcliff Dynalite/Homebridge mqtt Bridge - Version 4.0 Rain Detector for Window Closure - Gen
import json
import logging
import asyncio
import time
from dynalite_lib import Dynalite
import aioconsole
import asyncio_mqtt as aiomqtt
from dynalite_lib.const import(CONF_AREA, CONF_NAME, CONF_PRESET, CONF_CHANNEL)
from rain_monitor_Gen import RainMonitor

#logging.basicConfig(level=logging.DEBUG,
logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s")
LOG = logging.getLogger(__name__)

#OPTIONS_FILE = 'test/options.json'

loop = asyncio.get_event_loop()
dynalite = None

class DynaliteHBmqtt(object): #Class for Dynalite/Homebridge bridge via mqtt
    def __init__(self, dyn=None, config=None, hb_config=None, loop=None):
        from dynalite_controller_Gen import DynaliteController
        from homebridge_adapter_Gen import HomebridgeAdapter
        self.dyn = dyn
        self.cfg = config
        self.hb_cfg = hb_config
        self.loop = loop
        self.bom_geohash = config.get("bom_geohash")
        self.message_count = 0 # Set watchdog message count
        self.watchdog_file_name = '/home/pi/Dyna_hb/watchdog.log'
        self.hb_incoming_mqtt_topic = "homebridge/from/set" #Topic for messages from the Homebridge mqtt plugin
        self.hb_outgoing_mqtt_topic = "homebridge/to/set" #Topic for messages to the Homebridge mqtt plugin
        self.hb_switch_functions = ["Towels", "Floor"]
        self.mqtt_out_queue = asyncio.Queue(maxsize=1000)
        self.mqtt_client = None
        self.controller = DynaliteController(
            dyn=self.dyn,
            cfg=self.cfg,
            hb_cfg=self.hb_cfg,
            outgoing_cb=self.outgoing_mqtt
            )
        self.hb_adapter = HomebridgeAdapter(self.controller)
         
    def in_message(self, test_mode=None): #Collect async console inputs for each of the test modes
        if test_mode is not None:
            self.safe_task(lambda: self._in_message(test_mode), "console_input")                      
    
    async def _in_message(self, test_mode):
        while True:
                if test_mode == "Area Preset":
                    self.man_area = int(await aioconsole.ainput("Area"))
                    self.man_preset = int(await aioconsole.ainput("Preset"))
                    self.dyn.devices[CONF_AREA][self.man_area].presetOn(self.man_preset)
                elif test_mode == "Channel Level":
                    self.man_area = int(await aioconsole.ainput("Area "))
                    self.man_channel = int(await aioconsole.ainput("Channel "))
                    self.man_level = float(await aioconsole.ainput("Level "))
                    self.dyn.devices[CONF_AREA][self.man_area].channel[self.man_channel].turnOn(brightness=self.man_level)
                else:
                    pass
        
    async def _incoming_mqtt(self): #Capture, filter and action relevant incoming Homebridge mqtt messages
        while True:
            try:
                async with aiomqtt.Client("<Your mqtt Broker IP Address>") as client:
                    async with client.messages() as messages:
                        await client.subscribe("#")
                        LOG.info("Subscribed to %s", "#")                        
                        async for message in messages:
                            try:
                                await self._handle_mqtt_message(message)
                            except Exception:
                                LOG.exception("MQTT message handler failed")
            except asyncio.CancelledError:
                raise
            except aiomqtt.MqttError as e:
                LOG.error("MQTT icoming connection lost: %s", e)
                await asyncio.sleep(2)
                            
    async def _handle_mqtt_message(self, message):
        self.message_count += 1
        if self.message_count > 200: # Write to watchdog file every 200 mqtt messages
            self.message_count = 0
            with open(self.watchdog_file_name, 'w') as f:
                f.write('dynapi script alive')
        if message.topic.matches(self.hb_incoming_mqtt_topic): #Provide for monitoring of multiple mqtt topics
            LOG.debug("Do something with " + str(message.topic) + " " + str(message.payload))
            try:
                parsed_json = json.loads(message.payload.decode("utf-8"))
            except Exception as e:
                LOG.warning("Invalid MQTT payload on %s: %r (%s)", message.topic, message.payload, e)
                return
            result = self.hb_adapter.handle_message(parsed_json)
            if result: #Provides the ability to update Homebridge button states after operation (e.g. showing a window has been opened/closed)
                self.outgoing_mqtt(result)
            
    def check_valid_hb_message(self, pb_parsed_json): #Caters for situations where there's a Dynalite button that has no matching Homebridge button
        valid_message = False
        for button in self.hb_cfg:
            if button["name"] == pb_parsed_json["name"] and button["service_name"] == pb_parsed_json["service_name"]:
                valid_message = True
        if not valid_message:
            LOG.debug("Trying to set an invalid Homebridge Button. Message ignored. Name: " + pb_parsed_json["name"] + " Service Name: " + pb_parsed_json["service_name"])
        return valid_message

    async def mqtt_publisher(self):
        while True:
            try:
                async with aiomqtt.Client("<Your mqtt Broker IP Address>") as client:
                    LOG.info("MQTT publisher connected")
                    while True:
                        topic, payload = await self.mqtt_out_queue.get()
                        await client.publish(topic, payload, qos=1, retain=False)
            except asyncio.CancelledError:
                raise
            except aiomqtt.MqttError as e:
                LOG.error("MQTT publish connection lost: %s", e)
                await asyncio.sleep(2)

    def outgoing_mqtt(self, pb_parsed_json, topic="homebridge/to/set"):
        if not self.check_valid_hb_message(pb_parsed_json):
            return
        payload = json.dumps(pb_parsed_json)
        try:
            self.mqtt_out_queue.put_nowait((topic, payload))
        except asyncio.QueueFull:
            LOG.warning("MQTT queue full, dropping message: %s", payload)

    async def _on_rain_detected(self, forecast_hour):
        chance = forecast_hour.get("rain", {}).get("chance", 0)
        LOG.info("Rain forecast %d%% this hour - closing North and South windows", chance)
        self.controller.close_rain_windows()

    async def _start_rain_monitor(self):
        monitor = RainMonitor(self.bom_geohash)
        await monitor.monitor(self._on_rain_detected)

    def safe_task(self, coro_factory, name):
        async def runner():
            while True:
                try:
                    await coro_factory()
                except Exception as e:
                    LOG.error("Task '%s' crashed: %s - restarting", name, e)
                    await asyncio.sleep(2)
        self.loop.create_task(runner())
                
def handleEvent(event=None, dynalite=None):
    event_json = json.loads(event.toJson())
    if event_json["eventType"] == "CHANNEL" and event_json["direction"] == "IN":
        hbmqtt.controller.update_hb_channel(event_json["data"])
        LOG.debug("Channel Event " + str(event_json["data"]))
    elif event_json["eventType"] == "PRESET" and event_json["direction"] == "IN":
        hbmqtt.controller.update_hb_preset(event_json["data"])
        LOG.debug("Preset Event " + str(event_json["data"]))

def handleConnect(event=None, dynalite=None):
    LOG.debug("Connected to Dynalite")
    hbmqtt.in_message(test_mode=None)
    # Incoming MQTT listener
    hbmqtt.safe_task(lambda: hbmqtt._incoming_mqtt(), "incoming_mqtt")
    hbmqtt.safe_task(lambda: hbmqtt.mqtt_publisher(), "mqtt_publisher")
    if hbmqtt.bom_geohash:
        hbmqtt.safe_task(lambda: hbmqtt._start_rain_monitor(), "rain_monitor")
    
if __name__ == '__main__':
    #Set up the config dictionary
    #"area" records the details of each dynalite area in a dictionary, referenced by dynalite area numbers
    #   "name" for the area records the name of that area
    #   "channel" records the details of each required channel in a dictionary, referenced by a number string that equates to the channel number
    #      "name" records the name of that channel
    #      "level" records the brightness level of that channel
    #		"Preset" records the current preset of that channel
    #      "cct" records the color temperature (using Homebridge's scale" for channels that have cct lights
    #   "preset" records the area's preset details in a dictionary, referenced by a string number that equates to the preset's number
    #      "name" records the name of the preset. Can be "Off", "Med", "Low" or "Warm".
    #      "state" records the state of that preset. Initialises with "" and can be set to "On" or "Off" 
    #   "level" for the area records the brightness level of that area for lights or the opened/closed on/off states of windows and switches
    #	 "Linked": maps the area to anoher area that is linked in Dynalite's configuration (e.g. there are Antumbra buttons that control an area containing channels that are a subset of another area)
    #		"Area" records the area number of the linked area
    #		"Channels" records a list of the channels that are linked to the other area
    #		"Master" set to True if the area is a Master area (i.e. contains the superset of channels) or set to False if it's Slave area (i.e. contains the subset of channels)
    
    cfg = {"area": {3: {"name": "Entry Light", "channel": {"1": {"name": "Ceiling Light", "level": 1, "Preset": "", "cct": 140}, "2": {"name": "Wall Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "Med", "state": ""}, "2": {"name":"On", "state": ""},
                                                                                                                                    "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}, "7": {"name": "Warm", "state": ""}},
                        "level": 1, "cct": 140},
                    4: {"name": "Comms Light", "channel": {"1": {"name": "Comms Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""}, "3": {"name":"Low", "state": ""},
                                                                                                                      "4": {"name": "Off", "state": ""}}, "level": 1},
                    5: {"name": "Powder Light", "channel": {"1": {"name": "Ceiling Light", "level": 1, "Preset": ""}, "2": {"name": "Vanity Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                                     "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    6: {"name": "Kitchen Light", "channel": {"1": {"name": "Kitchen Hallway Light", "level": 1, "Preset": "", "cct": 140}, "2": {"name": "Kitchen Downlights", "level": 1, "Preset": "", "cct": 140}, "3": {"name": "Kitchen Pendant Light", "level": 1, "Preset": ""},
                                                             "5": {"name": "Kitchen Ceiling Light", "level": 1, "Preset": "", "cct": 140}, "6": {"name": "Kitchen Cooktop Light", "level": 1, "Preset": ""}},
                        "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""}, "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}, "7": {"name": "Warm", "state": ""}}, "level": 1, "cct": 140, "Linked": {"Area": 23, "Channels": [2, 3], "Master": True}},
                    7: {"name": "Appliance Light", "channel": {"4": {"name": "Appliance Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""}, "3": {"name":"Low", "state": ""},
                                                                                                                      "4": {"name": "Off", "state": ""}}, "level": 1},
                    8: {"name": "Living Light", "channel": {"1": {"name": "Living Light", "level": 1, "Preset": "", "cct": 140}}, "preset": {"1": {"name": "Low", "state": ""}, "2": {"name":"On", "state": ""}, "3": {"name":"Med", "state": ""},
                                                                                                                       "4": {"name": "Off", "state": ""}, "6": {"name": "Warm", "state": ""}}, "level": 1, "cct": 140},
                    9: {"name": "Dining Light", "channel": {"3": {"name": "TV Light", "level": 1, "Preset": ""}, "4": {"name": "Dining Pendant Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                                        "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    10: {"name": "Main Light", "channel": {"1": {"name": "Entry Light", "level": 1, "Preset": ""}, "2": {"name": "Wall Light", "level": 1, "Preset": ""}, "3": {"name": "Pendant Light", "level": 1, "Preset": ""}, "4": {"name": "Ceiling Light", "level": 1, "Preset": ""},
                                                           "5": {"name": "Left Bedside Light", "level": 1, "Preset": ""}, "6": {"name": "Right Bedside Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                                                "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1, "Linked": {"Area": 24, "Channels": [5, 6], "Master": True}},
                    11: {"name": "Main Ensuite Light", "channel": {"1": {"name": "Main Ensuite Shower Light", "level": 1, "Preset": ""}, "2": {"name": "Main Ensuite Vanity Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                                           "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    12: {"name": "Front Balcony Light", "channel": {"1": {"name": "North Balcony Light", "level": 1, "Preset": ""}, "2": {"name": "South Balcony Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""},
                                                                                                                                                                                          "2": {"name":"Med", "state": ""},
                                                                                                                                                                                          "3": {"name":"Low", "state": ""},
                                                                                                                                                                                          "4": {"name": "Off", "state": ""}}, "level": 1},
                    13: {"name": "Laundry Light", "channel": {"1": {"name": "Ceiling Light", "level": 1, "Preset": ""}, "2": {"name": "Benchtop Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                                         "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    14: {"name": "South Light",  "channel": {"1": {"name": "Ceiling Light", "level": 1, "Preset": ""}, "2": {"name": "Pendant Light", "level": 1, "Preset": ""}, "3": {"name": "Left Bedside Light", "level": 1, "Preset": ""},
                                                             "4": {"name": "Right Bedside Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""}, "3": {"name":"Low", "state": ""},
                                                                                                                              "4": {"name": "Off", "state": ""}}, "level": 1, "Linked": {"Area": 26, "Channels": [3, 4], "Master": True}},
                    15: {"name": "South Ensuite Light", "channel": {"1": {"name": "Ceiling Light", "level": 1, "Preset": ""}, "2": {"name": "Vanity Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": "", "state": ""},
                                                                                                                                                                             "2": {"name":"Med", "state": ""}, "3": {"name":"Low", "state": ""},
                                                                                                                                                                             "4": {"name": "Off", "state": ""}}, "level": 1},
                    16: {"name": "South Robe Light", "channel": {"1": {"name": "Ceiling Light", "level": 1, "Preset": ""}, "2": {"name": "LED Strip Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                                             "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    17: {"name": "Rear Balcony Light", "channel": {"1": {"name": "Rear Balcony Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    18: {"name": "Study Light", "channel": {"1": {"name": "Pendant", "level": 1, "Preset": ""}, "2": {"name": "Ceiling LED", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                              "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    19: {"name": "North Light", "channel": {"1": {"name": "Desk Light", "level": 1, "Preset": ""}, "2": {"name": "Ceiling Light", "level": 1, "Preset": ""}, "3": {"name": "Pendant Light", "level": 1, "Preset": ""}, "4": {"name": "Left Bedside Light", "level": 1, "Preset": ""},
                                                            "5": {"name": "Right Bedside Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name": "Med", "state": ""}, "3": {"name":"Low", "state": ""},
                                                                                                                          "4": {"name": "Off", "state": ""}}, "level": 1, "Linked": {"Area": 25, "Channels": [4, 5], "Master": True}},
                    20: {"name": "North Ensuite Light", "channel": {"1": {"name": "Ceiling Light", "level": 1, "Preset": ""}, "2": {"name": "Vanity Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "2": {"name":"Med", "state": ""},
                                                                                                                                                                             "3": {"name":"Low", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    23: {"name": "Kitchen Economy Light", "channel": {"2": {"name": "Kitchen Downlights", "level": 1, "Preset": "", "cct": 140}, "3": {"name": "Kitchen Pendant Light", "level": 1, "Preset": ""}}, "preset": {"9": {"name": "On", "state": ""}, "8": {"name": "Warm", "state": ""},
                                                                                                                                                                                       "4": {"name": "Off", "state": ""}}, "level": 1, "cct": 140, "level": 1, "Linked": {"Area": 6, "Channels": [2, 3], "Master": False}},
                    24: {"name": "Main Bedside Lights", "channel": {"5": {"name": "Left Bedside Light", "level": 1, "Preset": ""}, "6": {"name": "Right Bedside Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1, "Linked": {"Area": 10, "Channels": [5, 6], "Master": False}},
                    25: {"name": "North Bedside Lights", "channel": {"4": {"name": "Left Bedside Light", "level": 1, "Preset": ""}, "5": {"name": "Right Bedside Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1, "Linked": {"Area": 19, "Channels": [4, 5], "Master": False}},
                    26: {"name": "South Bedside Lights", "channel": {"3": {"name": "Left Bedside Light", "level": 1, "Preset": ""}, "4": {"name": "Right Bedside Light", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1, "Linked": {"Area": 14, "Channels": [3, 4], "Master": False}},
                    32: {"name": "Main Ensuite Towels", "channel": {"1": {"name": "Main Ensuite Towels", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    33: {"name": "Main Ensuite Floor", "channel": {"1": {"name": "Main Ensuite Floor", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    34: {"name": "South Ensuite Towels", "channel": {"1": {"name": "South Ensuite Towels", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    35: {"name": "South Ensuite Floor", "channel": {"1": {"name": "South Ensuite Floors", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    36: {"name": "North Ensuite Towels", "channel": {"1": {"name": "North Ensuite Towels", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    37: {"name": "North Ensuite Floor", "channel": {"1": {"name": "North Ensuite Floor", "level": 1, "Preset": ""}}, "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1},
                    48: {"name": "Main Window", "preset": {"1": {"name": "Open", "state": ""}, "4": {"name": "Close", "state": ""}}, "level": 1},
                    49: {"name": "South Window", "preset": {"1": {"name": "Open", "state": ""}, "4": {"name": "Close", "state": ""}}, "level": 1},
                    59: {"name": "North Window", "preset": {"1": {"name": "Open", "state": ""}, "4": {"name": "Close", "state": ""}}, "level": 1},
                    140: {"name": "South Shutters", "preset": {"1": {"name": "Open", "state": ""}, "4": {"name": "Close", "state": ""}}, "level": 1},
                    141: {"name": "Study Shutters", "preset": {"1": {"name": "Open", "state": ""}, "4": {"name": "Close", "state": ""}}, "level": 1},
                    142: {"name": "North Shutters", "preset": {"1": {"name": "Open", "state": ""}, "4": {"name": "Close", "state": ""}}, "level": 1},
                    143: {"name": "Main Ensuite Shutters", "preset": {"1": {"name": "Open", "state": ""}, "4": {"name": "Close", "state": ""}}, "level": 1},
                    148: {"name": "Main Good Morning", "preset": {"1": {"name": "On", "state": ""}, "4": {"name": "Off", "state": ""}}, "level": 1}},
           "host": "<Your Dynalite Gateway IP Address>", "port": 8008, "autodiscover": True, "log_level": "logging.INFO", "log_formatter": '"[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"',
           "bom_geohash": "r3gx2y"}
    
    #Set up the Homebridge config list to mirror how the Homebridge mqtt plug-in's accessories have been configured via Node-RED or the plug-in's homebridge/to/add and homebridge/to/add/service mqtt topics.
    #"name" is set to name of the dynalite area's name to be controlled by the respective button.
    #"service_name" is identical to "name" for Homebridge buttons that control dynalite area presets. "service_name" is set to the dynalite area's channel name for buttons that control channels in the respective dynalite area.
    hb_cfg = [{"name":"Living Light","service_name":"Living Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}, "ColorTemperature": {}}},
              {"name":"Kitchen Light","service_name":"Kitchen Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}, "ColorTemperature": {}}},
              {"name":"Kitchen Economy Light","service_name":"Kitchen Economy Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}, "ColorTemperature": {}}},
              {"name":"Kitchen Light","service_name":"Kitchen Downlights","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}, "ColorTemperature": {}}},
              {"name":"Kitchen Light","service_name":"Kitchen Hallway Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}, "ColorTemperature": {}}},
              {"name":"Kitchen Light","service_name":"Kitchen Ceiling Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}, "ColorTemperature": {}}},
              {"name":"Kitchen Light","service_name":"Kitchen Pendant Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Kitchen Light","service_name":"Kitchen Cooktop Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Appliance Light","service_name":"Appliance Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Laundry Light","service_name":"Laundry Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Entry Light","service_name":"Entry Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}, "ColorTemperature": {}}},
              {"name":"Powder Light","service_name":"Powder Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Dining Light","service_name":"Dining Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Dining Light","service_name":"TV Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Dining Light","service_name":"Dining Pendant Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Main Light","service_name":"Main Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Main Light","service_name":"Right Bedside Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Main Light","service_name":"Left Bedside Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Main Bedside Lights","service_name":"Main Bedside Lights","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Main Window","service_name":"Main Window","service_type":"Window", "characteristics_properties": {"TargetPosition": {"minStep": 100}}},
              {"name":"Main Ensuite Light","service_name":"Main Ensuite Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Main Ensuite Light","service_name":"Main Ensuite Shower Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Main Ensuite Towels","service_name":"Main Ensuite Towels","service_type":"Switch", "characteristics_properties": {}},
              {"name":"Main Ensuite Floor","service_name":"Main Ensuite Floor","service_type":"Switch", "characteristics_properties": {}},
              {"name":"Study Light","service_name":"Study Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"South Light","service_name":"South Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"South Robe Light","service_name":"South Robe Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"South Window","service_name":"South Window","service_type":"Window", "characteristics_properties": {"TargetPosition": {"minStep": 100}}},
              {"name":"South Ensuite Light","service_name":"South Ensuite Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"South Ensuite Towels","service_name":"South Ensuite Towels","service_type":"Switch", "characteristics_properties": {}},
              {"name":"South Ensuite Floor","service_name":"South Ensuite Floor","service_type":"Switch", "characteristics_properties": {}},
              {"name":"North Light","service_name":"North Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"North Window","service_name":"North Window","service_type":"Window", "characteristics_properties": {"TargetPosition": {"minStep": 100}}},
              {"name":"North Ensuite Light","service_name":"North Ensuite Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"North Ensuite Towels","service_name":"North Ensuite Towels","service_type":"Switch", "characteristics_properties": {}},
              {"name":"North Ensuite Floor","service_name":"North Ensuite Floor","service_type":"Switch", "characteristics_properties": {}},
              {"name":"Rear Balcony Light","service_name":"Rear Balcony Light","service_type":"Lightbulb", "characteristics_properties": {}},
              {"name":"Front Balcony Light","service_name":"Front Balcony Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Front Balcony Light","service_name":"South Balcony Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Front Balcony Light","service_name":"North Balcony Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name":"Comms Light","service_name":"Comms Light","service_type":"Lightbulb", "characteristics_properties": {"Brightness": {}}},
              {"name": "Main Room Shades", "service_name": "Day Fresh", "service_type": "WindowCovering", "characteristics_properties": {"TargetPosition": {"minStep": 10}}},
              {"name": "Main Ensuite Shutters", "service_name": "Main Ensuite Shutters", "service_type": "WindowCovering", "characteristics_properties": {"TargetPosition": {"minStep": 100}}},
              {"name": "Study Shutters", "service_name": "Study Shutters", "service_type": "WindowCovering", "characteristics_properties": {"TargetPosition": {"minStep": 100}}},
              {"name": "South Shutters", "service_name": "South Shutters", "service_type": "WindowCovering", "characteristics_properties": {"TargetPosition": {"minStep": 100}}},
              {"name": "North Shutters", "service_name": "North Shutters", "service_type": "WindowCovering", "characteristics_properties": {"TargetPosition": {"minStep": 100}}}]

    dynalite = Dynalite(config=cfg, loop=loop) #Create Dynalite object
    hbmqtt = DynaliteHBmqtt(dyn=dynalite, config=cfg, hb_config=hb_cfg, loop=loop) #Create Dynalite Homebridge mqtt bridge object
    bcstr = dynalite.addListener(listenerFunction=handleEvent)
    bcstr.monitorEvent('*')
    onConnect = dynalite.addListener(listenerFunction=handleConnect)
    onConnect.monitorEvent('CONNECTED')
    dynalite.start()
    loop.run_forever()
        
    

     
    
