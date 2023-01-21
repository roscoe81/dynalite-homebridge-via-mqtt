#!/usr/bin/env python3
#Northcliff Dynalite/Homebridge mqtt Bridge - Version 1.3 Gen
import json
import logging
import asyncio
import time
from dynalite_lib import Dynalite
import aioconsole
import asyncio_mqtt as aiomqtt
from dynalite_lib.const import(CONF_AREA, CONF_NAME, CONF_PRESET, CONF_CHANNEL)

#logging.basicConfig(level=logging.DEBUG,
logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s")
LOG = logging.getLogger(__name__)

loop = asyncio.get_event_loop()
dynalite = None

class DynaliteHBmqtt(object): #Class for Dynalite/Homebridge bridge via mqtt
    def __init__(self, dyn=None, config=None, loop=None):
        self.dyn = dyn
        self.cfg = config
        self.loop = loop
        self.hb_incoming_mqtt_topic = "homebridge/from/set" #Topic for messages from the Homebridge mqtt plugin
        self.hb_outgoing_mqtt_topic = "homebridge/to/set" #Topic for messages to the Homebridge mqtt plugin
        
    def identify_area_presets(self, area_name): #Return an area preset and its on/open, off/close and warm cct presets for a specified area's name
        target_area = None
        on_preset = None
        off_preset = None
        warm_preset = None
        for area in self.cfg[CONF_AREA]:
            if area_name == self.cfg[CONF_AREA][area][CONF_NAME]:
                target_area = area
                for preset in self.cfg[CONF_AREA][area][CONF_PRESET]:
                    if self.cfg[CONF_AREA][area][CONF_PRESET][preset][CONF_NAME] == "On" or self.cfg[CONF_AREA][area][CONF_PRESET][preset][CONF_NAME] == "Open":
                        on_preset = preset
                    elif self.cfg[CONF_AREA][area][CONF_PRESET][preset][CONF_NAME] == "Off" or self.cfg[CONF_AREA][area][CONF_PRESET][preset][CONF_NAME] == "Close":
                        off_preset = preset
                    elif self.cfg[CONF_AREA][area][CONF_PRESET][preset][CONF_NAME] == "Warm":
                        warm_preset = preset
        return target_area, off_preset, on_preset, warm_preset
    
    def identify_area_channels(self, area): #Return a list of the channels within a specified area
        target_channels = []
        if CONF_CHANNEL in self.cfg[CONF_AREA][area]:
            for channel in self.cfg[CONF_AREA][area][CONF_CHANNEL]:
                target_channels.append(int(channel))
        return target_channels
    
    def identify_target_channel(self, area, channel_name): #Return an area's channel for a specified channel name within that area
        target_channel = None
        if CONF_CHANNEL in self.cfg[CONF_AREA][area]:
            for channel in self.cfg[CONF_AREA][area][CONF_CHANNEL]:
                if CONF_NAME in self.cfg[CONF_AREA][area][CONF_CHANNEL][channel]:
                    for channel in self.cfg[CONF_AREA][area][CONF_CHANNEL]:
                        if channel_name == self.cfg[CONF_AREA][area][CONF_CHANNEL][channel][CONF_NAME]:
                            target_channel = channel
        return int(target_channel)
                            
    def in_message(self, test_mode=None): #Create an async loop task when in console test mode
        if test_mode != None:
            self.loop.create_task(self._in_message(test_mode))
        
    async def _in_message(self, test_mode): #Collect async console inputs for each of the test modes
        if test_mode != None:
            while True:
                if test_mode == "Area Preset":
                    self.man_area = int(await aioconsole.ainput("Area"))
                    self.man_preset = int(await aioconsole.ainput(CONF_PRESET))
                    self.dyn.devices[CONF_AREA][self.man_area].presetOn(self.man_preset)
                elif test_mode == "Channel Level":
                    self.man_area = int(await aioconsole.ainput("Area "))
                    self.man_channel = int(await aioconsole.ainput("Channel "))
                    self.man_level = float(await aioconsole.ainput("Level "))
                    self.devices[CONF_AREA][self.man_area].channel[self.man_channel].turnOn(brightness=self.man_level)
            
    def mqtt(self): #Create an async loop task for mqtt message capture
        self.loop.create_task(self._mqtt())
        
    async def _mqtt(self): #Capture, filter and action relevant incoming Homebridge mqtt messages
        async with aiomqtt.Client("<Your mqtt broker IP address>") as client:
            async with client.messages() as messages:
                await client.subscribe(self.hb_incoming_mqtt_topic)
                async for message in messages:
                    if message.topic.matches(self.hb_incoming_mqtt_topic): #Provide for monitoring of multiple mqtt topics
                        LOG.debug("Do something with " + str(message.topic) + " " + str(message.payload))
                        decoded_payload = str(message.payload.decode("utf-8"))
                        parsed_json = json.loads(decoded_payload)
                        if "service_type" in parsed_json and "characteristic" in parsed_json:
                            if parsed_json["service_type"] == "Window" and parsed_json["characteristic"] == "TargetPosition":
                                LOG.debug("Operate Window: " + str(parsed_json))
                                pb_parsed_json = self.operate_window(parsed_json)
                            elif parsed_json["service_type"] == "Lightbulb":
                                LOG.debug("Operate Light: " + str(parsed_json))
                                pb_parsed_json = self.operate_light(parsed_json)
                            elif parsed_json["service_type"] == "Switch":
                                LOG.debug("Operate Switch: " + str(parsed_json))
                                pb_parsed_json = self.operate_switch(parsed_json)
                        if pb_parsed_json != None:
                            await client.publish(self.hb_outgoing_mqtt_topic, payload = json.dumps(pb_parsed_json)) #Send updated accessory state to Homebridge when necessary                    
                    
    def operate_window(self, parsed_json):
        target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(parsed_json["name"])
        LOG.debug("Operating " + parsed_json["name"])
        LOG.debug("Target Area: " + str(target_area) + " Off Preset: " + str(off_preset) + " On Preset: " + str(on_preset) + " Warm Preset: " + str(warm_preset))
        if target_area == None or on_preset == None or off_preset == None:
            LOG.info(parsed_json["name"] + " and/or its presets not found in config")
            return None
        else:
            if parsed_json["value"] == 0:
                target_preset = off_preset
                window_action = "closing"
            else:
                target_preset = on_preset
                window_action = "opening"
        LOG.info(parsed_json["name"] + " " + window_action + ". Area " + str(target_area) + ", Preset " + target_preset)
        self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset))
        publish_parsed_json = {}
        publish_parsed_json["name"] = parsed_json["name"]
        publish_parsed_json["service_name"] = parsed_json["service_name"]
        publish_parsed_json["characteristic"] = "CurrentPosition"
        publish_parsed_json["value"] = parsed_json["value"]
        return publish_parsed_json
    
    def operate_switch(self, parsed_json):
        target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(parsed_json["name"])
        LOG.debug("Operating " + parsed_json["name"])
        LOG.debug("Target Area: " + str(target_area) + " Off Preset: " + str(off_preset) + " On Preset: " + str(on_preset) + " Warm Preset: " + str(warm_preset))
        if target_area == None or on_preset == None or off_preset == None:
            LOG.info(parsed_json["name"] + " and/or its presets not found in config")
            return None
        else:
            if parsed_json["value"] == 0:
                target_preset = off_preset
                switch_action = "turning off"
            else:
                target_preset = on_preset
                switch_action = "turning on"
        LOG.info(parsed_json["name"] + " " + switch_action + ". Area " + str(target_area) + ", Preset " + target_preset)
        self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset))
        return None
    
    def operate_light(self, parsed_json):
        target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(parsed_json["name"])
        LOG.debug("Operating " + parsed_json["service_name"])
        LOG.debug("Target Area: " + str(target_area) + " Off Preset: " + str(off_preset) + " On Preset: " + str(on_preset) + " Warm Preset: " + str(warm_preset))
        if target_area != None and on_preset != None and off_preset != None:
            if parsed_json["name"] == parsed_json["service_name"]: #Unequal when operating a light within an area or invoking a warm cct preset
                operate_entire_area = True
                warm_cct = False
            else:
                if "Warm" not in parsed_json["service_name"]:
                    warm_cct = False
                    operate_entire_area = False
                    target_one_channel = self.identify_target_channel(int(target_area), parsed_json["service_name"])
                    if target_one_channel == None:
                        LOG.info(parsed_json["service_name"] + " not found in config")
                        return None
                else:
                    warm_cct = True
                    operate_entire_area = True
            if parsed_json["characteristic"] == "On":
                if parsed_json["value"] and not warm_cct:
                    target_preset = on_preset
                    light_action = "turning on"
                elif parsed_json["value"] and warm_cct:
                    target_preset = warm_preset
                    light_action = "setting to warm"
                else:
                    target_preset = off_preset
                    light_action = "turning off"
                if operate_entire_area:
                    LOG.info(parsed_json["name"] + " " + light_action + ". Area " + str(target_area) + ", Preset " + target_preset)
                    LOG.debug("Driving Light. Target Area: " + str(target_area) + " Target Preset: " + str(target_preset))
                    self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset))
                else:
                    if parsed_json["value"]:
                        hb_brightness = 1
                        light_action = "turning on"
                    else:
                        hb_brightness = 0
                        light_action = "turning off"
                    LOG.debug("Targeted Channel: " + str(target_one_channel))
                    LOG.info(parsed_json["service_name"] + " " + light_action + ". Area " + str(target_area) + ", Channel " + str(target_one_channel))
                    self.dyn.devices[CONF_AREA][target_area].channel[target_one_channel].turnOn(brightness=hb_brightness)
            elif parsed_json["characteristic"] == "Brightness":
                hb_brightness = parsed_json["value"]/100
                light_action = "brightness changing to "
                if operate_entire_area:
                    target_channels = self.identify_area_channels(target_area)
                    if target_channels != []:
                        for target_channel in target_channels:
                            LOG.debug("Targeted Channel: " + str(target_channel))
                            LOG.info(self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)][CONF_NAME] + " " + light_action + str(parsed_json["value"]) + "%. Area " + str(target_area) + ", Channel " + str(target_channel))
                            self.dyn.devices[CONF_AREA][target_area].channel[target_channel].turnOn(brightness=hb_brightness)
                else:
                    LOG.info(self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_one_channel)][CONF_NAME] + " " + light_action + str(parsed_json["value"]) + "%. Area " + str(target_area) + ", Channel " + str(target_one_channel))
                    self.dyn.devices[CONF_AREA][target_area].channel[target_one_channel].turnOn(brightness=hb_brightness)                      
            else:
                pass         
        else:
            LOG.info(parsed_json["name"] + " and/or its presets not found in config")
        return None

def handleEvent(event=None, dynalite=None):
    LOG.debug(event.toJson())

def handleConnect(event=None, dynalite=None):
    LOG.info("Connected to Dynalite")
    hbmqtt.in_message(test_mode=None) #Use for testing via console. Starts console input async task loop. Use test_mode="Area Preset" for testing area presets, test_mode="Channel Level" for testing channel levels or test_mode=None to disable.
    hbmqtt.mqtt() # Start Homebridge mqtt async task loop
    
if __name__ == '__main__':
    cfg = {"area": {3: {"name": "Entry Light", "channel": {"1": {"name": "Ceiling Light"}, "2": {"name": "Wall Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    4: {"name": "Comms Light", "channel": {"1": {"name": "Ceiling Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    5: {"name": "Powder Light", "channel": {"1": {"name": "Ceiling Light"}, "2": {"name": "Vanity Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    6: {"name": "Kitchen Light", "channel": {"1": {"name": "Kitchen Hallway Light"}, "2": {"name": "Kitchen Downlights"}, "3": {"name": "Kitchen Pendant Light"}, "5": {"name": "Kitchen Ceiling Light"},
                                                             "6": {"name": "Kitchen Cooktop Light"}},
                        "preset": {"1": {"name": "Med"}, "2": {"name":"On"}, "3": {"name":"Low"}, "4": {"name": "Off"}, "7": {"name": "Warm"}}},
                    7: {"name": "Appliance Light", "channel": {"4": {"name": "LED Strip"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    8: {"name": "Living Light", "channel": {"1": {"name": "Ceiling Light"}}, "preset": {"1": {"name": "Low"}, "2": {"name":"On"}, "3": {"name":"Med"}, "4": {"name": "Off"}, "6": {"name": "Warm"}}},
                    9: {"name": "Dining Light", "channel": {"3": {"name": "TV Light"}, "4": {"name": "Dining Pendant Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    10: {"name": "Main Light", "channel": {"1": {"name": "Entry Light"}, "2": {"name": "Wall Light"}, "3": {"name": "Pendant Light"}, "4": {"name": "Ceiling Light"}, "5": {"name": "Left Bedside Light"}, "6": {"name": "Right Bedside Light"}},
                         "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    11: {"name": "Main Ensuite Light", "channel": {"1": {"name": "Shower Light"}, "2": {"name": "Vanity Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    12: {"name": "Front Balcony Light", "channel": {"1": {"name": "North Balcony Light"}, "2": {"name": "South Balcony Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    13: {"name": "Laundry Light", "channel": {"1": {"name": "Ceiling Light"}, "2": {"name": "Benchtop Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    14: {"name": "South Light",  "channel": {"1": {"name": "Pendant Light"}, "2": {"name": "Ceiling Light"}, "3": {"name": "Left Bedside Light"}, "4": {"name": "Right Bedside Light"}},
                         "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    15: {"name": "South Ensuite Light", "channel": {"1": {"name": "Ceiling Light"}, "2": {"name": "Vanity Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    16: {"name": "South Robe Light", "channel": {"1": {"name": "Ceiling Light"}, "2": {"name": "LED Strip Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    17: {"name": "Rear Balcony Light", "channel": {"1": {"name": "Ceiling Light"}}, "preset": {"1": {"name": "On"}, "4": {"name": "Off"}}},
                    18: {"name": "Study Light", "channel": {"1": {"name": "Pendant"}, "2": {"name": "Ceiling LED"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    19: {"name": "North Light", "channel": {"1": {"name": "Desk Light"}, "2": {"name": "Ceiling Light"}, "3": {"name": "Pendant Light"}, "4": {"name": "Left Bedside Light"}, "5": {"name": "Right Bedside Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    20: {"name": "North Ensuite Light", "channel": {"1": {"name": "Ceiling Light"}, "2": {"name": "Vanity Light"}}, "preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    23: {"name": "Kitchen Economy Light", "channel": {"1": {"name": "Ceiling Light"}, "2": {"name": "Vanity Light"}},"preset": {"1": {"name": "On"}, "2": {"name":"Med"}, "3": {"name":"Low"}, "4": {"name": "Off"}}},
                    32: {"name": "Main Ensuite Towels", "preset": {"1": {"name": "On"}, "4": {"name": "Off"}}},
                    33: {"name": "Main Ensuite Floor", "preset": {"1": {"name": "On"}, "4": {"name": "Off"}}},
                    34: {"name": "South Ensuite Towels", "preset": {"1": {"name": "On"}, "4": {"name": "Off"}}},
                    35: {"name": "South Ensuite Floor", "preset": {"1": {"name": "On"}, "4": {"name": "Off"}}},
                    36: {"name": "North Ensuite Towels", "preset": {"1": {"name": "On"}, "4": {"name": "Off"}}},
                    37: {"name": "North Ensuite Floor", "preset": {"1": {"name": "On"}, "4": {"name": "Off"}}},
                    48: {"name": "Main Window", "preset": {"1": {"name": "Open"}, "4": {"name": "Close"}}},
                    49: {"name": "South Window", "preset": {"1": {"name": "Open"}, "4": {"name": "Close"}}},
                    59: {"name": "North Window", "preset": {"1": {"name": "Open"}, "4": {"name": "Close"}}}},
           "host": "<Your RS485 to IP gateway IP address>", "port": "<Your RS485 to IP gateway Port Number e.g. 8008>", "autodiscover": True, "log_level": "logging.INFO", "log_formatter": '"[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"'} #Replace with your configuration

    dynalite = Dynalite(config=cfg, loop=loop) #Create Dynalite object
    hbmqtt = DynaliteHBmqtt(dyn=dynalite, config=cfg, loop=loop) #Create Dynalite Homebridge mqtt bridge object
    bcstr = dynalite.addListener(listenerFunction=handleEvent)
    bcstr.monitorEvent('*')
    onConnect = dynalite.addListener(listenerFunction=handleConnect)
    onConnect.monitorEvent('CONNECTED')
    dynalite.start()
    loop.run_forever()

     
    
