#!/usr/bin/env python3
#Northcliff Dynalite Controller - Version 2.0 Support Rain Detector for Window Closure - Gen
import logging
from dynalite_lib.const import(CONF_AREA, CONF_NAME, CONF_PRESET, CONF_CHANNEL)

LOG = logging.getLogger(__name__)

class DynaliteController:
    def __init__(self, dyn, cfg, hb_cfg, outgoing_cb):
        self.dyn = dyn
        self.cfg = cfg
        self.hb_cfg = hb_cfg
        self.outgoing_cb = outgoing_cb # Replaces outgoing_mqtt
        
    def identify_area_presets(self, area_name): #Return an area preset and its on/opened, off/closed and warm cct presets for a specified area's name
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
    
    def identify_target_channel(self, area, channel_name): #Return an area's channel number for a specified channel name within that area
        target_channel = None
        if CONF_CHANNEL in self.cfg[CONF_AREA][area]:
            for channel in self.cfg[CONF_AREA][area][CONF_CHANNEL]:
                if CONF_NAME in self.cfg[CONF_AREA][area][CONF_CHANNEL][channel]:
                    for channel in self.cfg[CONF_AREA][area][CONF_CHANNEL]:
                        if channel_name == self.cfg[CONF_AREA][area][CONF_CHANNEL][channel][CONF_NAME]:
                            target_channel = channel
        return target_channel
    
    def identify_non_target_presets(self, target_area, target_preset): #Return the list of presets that aren't targeted
        non_target_presets = []
        for area in self.cfg[CONF_AREA]:
            if area == target_area:
                for preset in self.cfg[CONF_AREA][area][CONF_PRESET]:
                    if preset != target_preset:
                        non_target_presets.append(preset)
        return non_target_presets
    
    def match_linked_area(self, area_updated, off_preset, on_preset): # Match Slave Area Dynalite and HB button states for Linked Channels to the Master Area's states
        if "Linked" in self.cfg[CONF_AREA][area_updated]:
            LOG.debug("Linked Channel to Area Update " + str(self.cfg[CONF_AREA][area_updated]))
            if self.cfg[CONF_AREA][area_updated]["Linked"]["Master"]:
                all_linked_channels_on = True
                all_linked_channels_off = True
                for channel in self.cfg[CONF_AREA][area_updated]["Linked"]["Channels"]:
                    LOG.debug("Channel " + str(channel) + " " + str(self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][str(channel)]["Preset"]))
                    if str(self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][str(channel)]["Preset"]) != off_preset:
                        all_linked_channels_off = False
                    if str(self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][str(channel)]["Preset"]) != on_preset:
                        all_linked_channels_on = False
                LOG.debug("All Linked Channels Off " + str(all_linked_channels_off) + " All Linked Channels On " + str(all_linked_channels_on))
                # Update Slave Area Dynalite and HB states if all linked Master Channels are either on or off
                if all_linked_channels_on:
                    pbln_parsed_json = {}
                    pbln_parsed_json["characteristic"] = "On"
                    pbln_parsed_json["name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_NAME]
                    pbln_parsed_json["service_name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_NAME]
                    pbln_parsed_json["value"] = True
                    LOG.debug("All Linked Channels are On " + str(pbln_parsed_json))
                    pb_parsed_json = self.operate_light(pbln_parsed_json, switch_entire_area=True, match_linked_area=False)
                    LOG.debug("HB Linked Area Message " + str(pbln_parsed_json))
                    self.outgoing_cb(pbln_parsed_json)
                elif all_linked_channels_off:
                    pblf_parsed_json = {}
                    pblf_parsed_json["characteristic"] = "On"
                    pblf_parsed_json["name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_NAME]
                    pblf_parsed_json["service_name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_NAME]
                    pblf_parsed_json["value"] = False
                    LOG.debug("All Linked Channels are Off " + str(pblf_parsed_json))
                    pb_parsed_json = self.operate_light(pblf_parsed_json, switch_entire_area=True, match_linked_area=False)
                    LOG.debug("HB Linked Area Message " + str(pblf_parsed_json))
                    self.outgoing_cb(pblf_parsed_json)

    def match_channel_presets(self, area, preset): #Match an area's channel presets and its channels' Homebridge button states to the area's preset state
        target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(self.cfg[CONF_AREA][area][CONF_NAME])
        hb_button_json = {} # Find relevant homebridge buttons for the area that's been preset
        for button_json in self.hb_cfg:
            if button_json["name"] == self.cfg[CONF_AREA][area][CONF_NAME]:
                hb_button_json = button_json
        if CONF_CHANNEL in self.cfg[CONF_AREA][area]:
            for channel in self.cfg[CONF_AREA][area][CONF_CHANNEL]: #Update Channel Presets to reflect new area preset
                LOG.debug("Old Channel Preset. Area: " + str(area) + " Channel: " + str(channel) + " Preset: " + str(self.cfg[CONF_AREA][area][CONF_CHANNEL][channel]["Preset"]))
                self.cfg[CONF_AREA][area][CONF_CHANNEL][channel]["Preset"] = str(preset)
                LOG.debug("New Channel Preset. Area: " + str(area) + " Channel: " + str(channel) + " Preset: " + str(self.cfg[CONF_AREA][area][CONF_CHANNEL][channel]["Preset"]))
                if hb_button_json != {}: # Update the channel homebridge buttons (if present)
                    if hb_button_json["service_name"] == self.cfg[CONF_AREA][area][CONF_CHANNEL][str(channel)][CONF_NAME]:
                        button_found = True
                        pb_parsed_json = {}
                        pb_parsed_json["name"] = hb_button_json["name"]
                        pb_parsed_json["service_name"] = hb_button_json["service_name"]
                        pb_parsed_json["characteristic"] = "On"
                        if str(preset) == off_preset:
                            pb_parsed_json["value"] = False
                            button_state = "Off"
                            LOG.debug("Update Area " + hb_button_json["name"] + "'s Homebridge " + hb_button_json["service_name"] + " button to " + button_state)
                            self.outgoing_cb(pb_parsed_json)
                        elif str(preset) == on_preset or str(preset) == warm_preset:
                            pb_parsed_json["value"] = True
                            button_state = "On"
                            LOG.debug("Update Area " + hb_button_json["name"] + "'s Homebridge " + hb_button_json["service_name"] + " button to " + button_state)
                            self.outgoing_cb(pb_parsed_json)
                        else:
                            LOG.info("Neither On, Off nor Warm presets selected")
                
    def match_linked_hb_channels(self, area_updated, light_state): # Match Homebridge Light buttons and Dynalite states for Linked Channels.
        if "Linked" in self.cfg[CONF_AREA][area_updated]:
            LOG.debug("Linked " + str(self.cfg[CONF_AREA][area_updated]))
            if self.cfg[CONF_AREA][area_updated]["Linked"]["Master"]: # If it's the Master Area, update the Slave Area's Dynalite setting and HB button
                pbl_parsed_json = {}
                pbl_parsed_json["characteristic"] = "On"
                pbl_parsed_json["name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_NAME]
                pbl_parsed_json["service_name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_NAME]
                pbl_parsed_json["value"] = light_state
                LOG.debug("Operate Light 1 " + str(pbl_parsed_json))
                pb_parsed_json = self.operate_light(pbl_parsed_json, switch_entire_area=True, match_linked_area=False)
                LOG.debug("HB1 Message " + str(pbl_parsed_json))
                self.outgoing_cb(pbl_parsed_json)
                for channel in self.cfg[CONF_AREA][area_updated]["Linked"]["Channels"]: # Update the Master Area's HB channel buttons
                    pbl1_parsed_json = {}
                    pbl1_parsed_json["characteristic"] = "On"
                    pbl1_parsed_json["name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                    pbl1_parsed_json["service_name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_CHANNEL][str(channel)][CONF_NAME]
                    pbl1_parsed_json["value"] = light_state
                    LOG.debug("HB2 Message " + str(pbl1_parsed_json))
                    self.outgoing_cb(pbl1_parsed_json)  
            else: # If it's the Slave Area, update the Master Area's Dynalite Channel and HB settings
                for channel in self.cfg[CONF_AREA][area_updated]["Linked"]["Channels"]:
                    pbl2_parsed_json = {}
                    pbl2_parsed_json["characteristic"] = "On"
                    pbl2_parsed_json["name"] = self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_NAME]
                    pbl2_parsed_json["service_name"] =self.cfg[CONF_AREA][self.cfg[CONF_AREA][area_updated]["Linked"]["Area"]][CONF_CHANNEL][str(channel)][CONF_NAME]
                    pbl2_parsed_json["value"] = light_state
                    pb_parsed_json = self.operate_light(pbl2_parsed_json, switch_entire_area=False, match_linked_area=False)
                    LOG.debug("HB3 Message " + str(pbl2_parsed_json))
                    self.outgoing_cb(pbl2_parsed_json)  

    def operate_light(self, parsed_json, switch_entire_area=False, match_linked_area=True): #Respond to a Homebridge operate light button when match_linked_area is True and set linked lights when matched_linked_area is False
        target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(parsed_json["name"])
        LOG.debug("Operating " + parsed_json["service_name"])
        LOG.debug("Target Area: " + str(target_area) + " Off Preset: " + str(off_preset) + " On Preset: " + str(on_preset) + " Warm Preset: " + str(warm_preset))
        if target_area != None and on_preset != None and off_preset != None:
            if parsed_json["name"] == parsed_json["service_name"]: # Unequal when operating a light within an area
                operate_entire_area = True
                if "cct" in self.cfg[CONF_AREA][target_area]:
                    cct = True
                else:
                    cct = False
            else:
                operate_entire_area = False
                target_one_channel = self.identify_target_channel(int(target_area), parsed_json["service_name"]) #Find the target channel
                if target_one_channel == None:
                    LOG.info(parsed_json["service_name"] + " not found in config")
                    return {}
                if "cct" in self.cfg[CONF_AREA][target_area][CONF_CHANNEL][target_one_channel]:
                    cct = True
                else:
                    cct = False
            if parsed_json["characteristic"] == "On": #If the light is being switched, without changing it's dimming level
                hb_brightness = self.cfg[CONF_AREA][target_area]["level"]
                if operate_entire_area:
                    if parsed_json["value"] and not cct: #Only cater for on state if the light isn't cct
                        target_preset = on_preset
                        non_target_presets = self.identify_non_target_presets(target_area, target_preset)
                        non_cct_light_action = "turning on"
                    elif parsed_json["value"] and cct: #Use use the light's cct state in cfg to determine whether it should be warm or cool when turned on
                        if self.cfg[CONF_AREA][target_area]["cct"] == "Warm":
                            target_preset = warm_preset
                            non_target_presets = self.identify_non_target_presets(target_area, target_preset)
                            non_cct_light_action = "turning on"
                            cct_light_action = "setting to warm"
                            self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset)) # Set to warm before setting level
                        else:
                            target_preset = on_preset
                            non_target_presets = self.identify_non_target_presets(target_area, target_preset)
                            non_cct_light_action = "turning on"
                            cct_light_action = "setting to cool"
                            self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset)) # Set to cool before setting level
                    else: #Set to off
                        target_preset = off_preset
                        non_target_presets = self.identify_non_target_presets(target_area, target_preset)
                        non_cct_light_action = "turning off"
                        cct_light_action = "turning off"
                        hb_brightness = 0
                    target_channels = self.identify_area_channels(target_area)
                    if target_channels != [] and not switch_entire_area: #Switch individual channels
                        for target_channel in target_channels:
                            if "cct" in self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)]:
                                light_action = cct_light_action
                            else:
                                light_action = non_cct_light_action
                            LOG.debug("Targeted Channel: " + str(target_channel))
                            LOG.info(parsed_json["name"] + " " + self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)][CONF_NAME] + " " + light_action + ". Area " + str(target_area) + ", Channel " + str(target_channel))
                            self.dyn.devices[CONF_AREA][target_area].channel[target_channel].turnOn(brightness=hb_brightness)
                            for button_json in self.hb_cfg:
                                if button_json["name"] == self.cfg[CONF_AREA][target_area][CONF_NAME] and button_json["service_name"] == self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)][CONF_NAME]:
                                    pb_parsed_json = {}
                                    pb_parsed_json["name"] = button_json["name"]
                                    pb_parsed_json["service_name"] = button_json["service_name"]
                                    pb_parsed_json["characteristic"] = "On"
                                    if hb_brightness == 0: #Turn off the Homebridge button for area channels that have their own button, when its area is turned off
                                        pb_parsed_json["value"] = False
                                    else:
                                        pb_parsed_json["value"] = True
                                    self.outgoing_cb(pb_parsed_json)                                    
                    self.cfg[CONF_AREA][target_area][CONF_PRESET][str(target_preset)]["state"] = "On"
                    if non_target_presets != []:
                        for preset in non_target_presets:
                            self.cfg[CONF_AREA][target_area][CONF_PRESET][str(preset)]["state"] = "Off"
                    self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset)) # Set area preset
                    if match_linked_area: #Prevents recursive loops
                        self.match_channel_presets(target_area, target_preset)
                        if target_preset == off_preset:
                            light_state = False
                        else:
                            light_state = True
                        LOG.debug("Calling match_linked_hb_channels " + str(target_area) + " " + str(light_state))
                        self.match_linked_hb_channels(target_area, light_state)
                else:
                    if parsed_json["value"]:
                        hb_brightness = self.cfg[CONF_AREA][target_area][CONF_CHANNEL][target_one_channel]["level"]
                        light_action = "turning on"
                        channel_preset = on_preset
                    else:
                        hb_brightness = 0
                        light_action = "turning off"
                        channel_preset = off_preset
                    LOG.debug("Old Channel Preset. Area: " + str(target_area) + " Channel: " + str(target_one_channel) + " Preset: " + str(self.cfg[CONF_AREA][target_area][CONF_CHANNEL][target_one_channel]["Preset"]))
                    self.cfg[CONF_AREA][target_area][CONF_CHANNEL][target_one_channel]["Preset"] = str(channel_preset)
                    LOG.debug("New Channel Preset. Area: " + str(target_area) + " Channel: " + str(target_one_channel) + " Preset: " + str(self.cfg[CONF_AREA][target_area][CONF_CHANNEL][target_one_channel]["Preset"]))
                    LOG.debug("Targeted Channel: " + str(target_one_channel))
                    LOG.info(parsed_json["name"] + " " + parsed_json["service_name"] + " " + light_action + ". Area " + str(target_area) + ", Channel " + target_one_channel)
                    self.dyn.devices[CONF_AREA][target_area].channel[int(target_one_channel)].turnOn(brightness=hb_brightness)
                    if match_linked_area: #Prevents recursive loops by only calling match_linked_area when operating the primary area
                        LOG.debug("Calling match_linked_area " + str(target_area) + " " + str(off_preset) + " " + str(on_preset))
                        self.match_linked_area(target_area, off_preset, on_preset)
            elif parsed_json["characteristic"] == "Brightness":
                hb_brightness = parsed_json["value"]/100
                light_action = "brightness changing to "
                if operate_entire_area:
                    target_channels = self.identify_area_channels(target_area)
                    if target_channels != []:
                        for target_channel in target_channels:
                            LOG.debug("Targeted Channel: " + str(target_channel))
                            LOG.info(parsed_json["name"] + " " + self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)][CONF_NAME] + " " + light_action + str(parsed_json["value"]) + "%. Area " + str(target_area) + ", Channel " + str(target_channel))
                            self.dyn.devices[CONF_AREA][target_area].channel[target_channel].turnOn(brightness=hb_brightness)
                            self.cfg[CONF_AREA][target_area]["level"] = hb_brightness
                            self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)]["level"] = hb_brightness
                else:
                    LOG.info(parsed_json["name"] + " " + self.cfg[CONF_AREA][target_area][CONF_CHANNEL][target_one_channel][CONF_NAME] + " " + light_action + str(parsed_json["value"]) + "%. Area " + str(target_area) + ", Channel " + target_one_channel)
                    self.dyn.devices[CONF_AREA][target_area].channel[int(target_one_channel)].turnOn(brightness=hb_brightness)
                    self.cfg[CONF_AREA][target_area][CONF_CHANNEL][target_one_channel]["level"] = hb_brightness
            elif parsed_json["characteristic"] == "ColorTemperature":
                if parsed_json["value"] < 250:
                    target_cct = "Cool"
                else:
                    target_cct = "Warm"
                if "cct" in self.cfg[CONF_AREA][target_area]: #Only make a change if the area is configured with cct lights
                    self.cfg[CONF_AREA][target_area]["cct"] = target_cct #Update area in config to request cct colour
                    non_cct_channels = [] #List channels that do not have cct lights
                    for channel in self.cfg[CONF_AREA][target_area][CONF_CHANNEL]:
                        if "cct" in self.cfg[CONF_AREA][target_area][CONF_CHANNEL][channel]:
                            self.cfg[CONF_AREA][target_area][CONF_CHANNEL][channel]["cct"] = target_cct
                        else:
                            non_cct_channels.append(channel)
                    drive_cct_change = False #Check if the area is already set to the requested cct colour. If not, update its config and flag that the area's preset is to be changed.
                    if target_cct == "Cool":
                        target_preset = on_preset
                        if self.cfg[CONF_AREA][target_area][CONF_PRESET][warm_preset]["state"] == "On":
                            drive_cct_change = True
                            cct_light_action = "setting to cool"
                            non_cct_light_action = "turning on"
                            self.cfg[CONF_AREA][target_area][CONF_PRESET][warm_preset]["state"] = "Off"
                            self.cfg[CONF_AREA][target_area][CONF_PRESET][on_preset]["state"] = "On"               
                    else:
                        target_preset = warm_preset
                        if self.cfg[CONF_AREA][target_area][CONF_PRESET][warm_preset]["state"] == "Off":
                            drive_cct_change = True
                            cct_light_action = "setting to warm"
                            non_cct_light_action = "turning on"
                            self.cfg[CONF_AREA][target_area][CONF_PRESET][warm_preset]["state"] = "On"
                            self.cfg[CONF_AREA][target_area][CONF_PRESET][on_preset]["state"] = "Off"
                    #print("cct", target_cct, drive_cct_change, target_preset, "warm preset", self.cfg[CONF_AREA][target_area][CONF_PRESET][warm_preset]["state"])
                    if drive_cct_change: #Change preset if a change is flagged and set brightness to previously set level
                        LOG.debug("Setting Area Preset " + target_preset)
                        self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset))
                        target_channels = self.identify_area_channels(target_area) #List the channels in the area
                        if not operate_entire_area:
                            target_one_channel = self.identify_target_channel(int(target_area), parsed_json["service_name"])
                            if target_one_channel == None:
                                LOG.info(parsed_json["name"] + " " + parsed_json["service_name"] + " channel not found in config when trying to set its colour temperature")
                                return {}
                        if target_channels != []:
                            for target_channel in target_channels:
                                LOG.debug("Targeted Channel: " + str(target_channel))
                                if operate_entire_area:
                                    hb_brightness = self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)]["level"]
                                    if str(target_channel) in non_cct_channels:
                                        LOG.info(self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)][CONF_NAME] + " " + non_cct_light_action + ". Area " + str(target_area) + ", Channel " + str(target_channel))
                                    else:
                                        LOG.info(self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)][CONF_NAME] + " " + cct_light_action + ". Area " + str(target_area) + ", Channel " + str(target_channel))
                                elif target_channel == int(target_one_channel):
                                    hb_brightness = self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)]["level"]
                                    LOG.info(parsed_json["name"] + " " + self.cfg[CONF_AREA][target_area][CONF_CHANNEL][str(target_channel)][CONF_NAME] + " " + cct_light_action + ". Area " + str(target_area) + ", Channel " + str(target_channel))
                                else:
                                    LOG.debug("Neither Entire Area nor Target Channel" + " " + cct_light_action + ". Area " + str(target_area) + ", Channel " + str(target_channel))
                                    hb_brightness = 0
                                self.dyn.devices[CONF_AREA][target_area].channel[target_channel].turnOn(brightness=hb_brightness)
            else:
                LOG.info("No valid light characteristic")
            return {}       
        else:
            LOG.info(parsed_json["name"] + " and/or its presets not found in config")
        return {}

    def operate_switch(self, parsed_json): #Respond to a Homebridge operate switch button
        target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(parsed_json["name"])
        LOG.debug("Operating " + parsed_json["name"])
        LOG.debug("Target Area: " + str(target_area) + " Off Preset: " + str(off_preset) + " On Preset: " + str(on_preset) + " Warm Preset: " + str(warm_preset))
        if target_area == None or on_preset == None or off_preset == None:
            LOG.info(parsed_json["name"] + " and/or its presets not found in config")
            return {}
        else:
            if parsed_json["value"] == 0:
                target_preset = off_preset
                non_target_preset = on_preset
                switch_action = "turning off"
            else:
                target_preset = on_preset
                non_target_preset = off_preset
                switch_action = "turning on"
        LOG.info(parsed_json["name"] + " " + switch_action + ". Area " + str(target_area) + ", Preset " + target_preset)
        self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset))
        self.cfg[CONF_AREA][int(target_area)][CONF_PRESET][str(target_preset)]["state"] = "On"
        self.cfg[CONF_AREA][int(target_area)][CONF_PRESET][str(non_target_preset)]["state"] = "Off"
        return {}

    def operate_window(self, parsed_json): #Respond to a Homebridge operate window button
        target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(parsed_json["name"])
        LOG.debug("Operating " + parsed_json["name"])
        LOG.debug("Target Area: " + str(target_area) + " Off Preset: " + str(off_preset) + " On Preset: " + str(on_preset) + " Warm Preset: " + str(warm_preset))
        if target_area == None or on_preset == None or off_preset == None:
            LOG.info(parsed_json["name"] + " and/or its presets not found in config")
            return None
        else:
            if parsed_json["value"] == 0:
                target_preset = off_preset
                non_target_preset = on_preset
                window_action = "closing"
            else:
                target_preset = on_preset
                non_target_preset = off_preset
                window_action = "opening"
        LOG.info(parsed_json["name"] + " " + window_action + ". Area " + str(target_area) + ", Preset " + target_preset)
        self.dyn.devices[CONF_AREA][int(target_area)].presetOn(int(target_preset))
        self.cfg[CONF_AREA][int(target_area)][CONF_PRESET][str(target_preset)]["state"] = "On"
        self.cfg[CONF_AREA][int(target_area)][CONF_PRESET][str(non_target_preset)]["state"] = "Off"
        pb_parsed_json = {}
        pb_parsed_json["name"] = parsed_json["name"]
        pb_parsed_json["service_name"] = parsed_json["service_name"]
        pb_parsed_json["characteristic"] = "CurrentPosition"
        pb_parsed_json["value"] = parsed_json["value"]
        return pb_parsed_json #Return a parsed_json that shows the window's post-command postion

    def close_rain_windows(self):
        rain_windows = {"North Window", "South Window"}
        for area in self.cfg[CONF_AREA]:
            area_name = self.cfg[CONF_AREA][area][CONF_NAME]
            if area_name in rain_windows:
                target_area, off_preset, on_preset, _ = self.identify_area_presets(area_name)
                if target_area is None or off_preset is None or on_preset is None:
                    LOG.warning("Rain: %s - presets not found in config, skipping", area_name)
                    continue
                open_state = self.cfg[CONF_AREA][area][CONF_PRESET][str(on_preset)].get("state", "Off")
                if open_state != "On":
                    LOG.info("Rain: %s is already closed, skipping", area_name)
                    continue
                parsed_json = {"name": area_name, "service_name": area_name, "value": 0}
                result = self.operate_window(parsed_json)
                if result:
                    self.outgoing_cb(result)
                LOG.info("Rain: closing %s", area_name)

    def update_hb_channel(self, event_data): #Update a channel-specific Homebridge button's state to match the state of its area's preset. Match any linked area's dynalite state.
        LOG.debug("Update HB Channel " + str(event_data))
        area_updated = None
        for area in self.cfg[CONF_AREA]: #Find area and preset that's been updated and capture its new state
            if area == event_data[CONF_AREA]:
                LOG.debug("Old area states " + str(self.cfg[CONF_AREA][area]))
                area_updated = area
        if area_updated != None:
            channel_updated = None
            if CONF_CHANNEL in self.cfg[CONF_AREA][area_updated]:
                for channel in self.cfg[CONF_AREA][area_updated][CONF_CHANNEL]:
                    if channel == str(event_data[CONF_CHANNEL]):
                        channel_updated = channel
                if channel_updated != None:
                    if event_data["action"] == "cmd": #Only respond to Dynalite command messages
                        LOG.debug("Update HB Channel " + str(event_data))
                        if CONF_PRESET in event_data:
                            target_preset = event_data[CONF_PRESET]
                            self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][channel_updated]["Preset"] = target_preset #Update config to record new channel state
                            LOG.debug("Updated", self.cfg[CONF_AREA][area_updated]["name"], "Channel Preset", self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][channel_updated])
                            target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(self.cfg[CONF_AREA][area_updated][CONF_NAME]) #Find On, Off and Warm presets
                            button_found = False
                            for button_json in self.hb_cfg: #Update Homebridge to show state of any channel-specific button in the updated area
                                if button_json["name"] == self.cfg[CONF_AREA][area_updated][CONF_NAME]:
                                    if button_json["service_name"] == self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][str(channel_updated)][CONF_NAME]:
                                        button_found = True
                                        pb_parsed_json = {}
                                        pb_parsed_json["name"] = button_json["name"]
                                        pb_parsed_json["service_name"] = button_json["service_name"]
                                        pb_parsed_json["characteristic"] = "On"
                                        if str(target_preset) == off_preset:
                                            pb_parsed_json["value"] = False
                                            button_state = "Off"
                                            LOG.debug("Update Area " + button_json["name"] + "'s Homebridge " + button_json["service_name"] + " button to " + button_state)
                                            self.outgoing_cb(pb_parsed_json)
                                        elif str(target_preset) == on_preset or str(target_preset) == warm_preset:
                                            pb_parsed_json["value"] = True
                                            button_state = "On"
                                            LOG.debug("Update Area " + button_json["name"] + "'s Homebridge " + button_json["service_name"] + " button to " + button_state)
                                            self.outgoing_cb(pb_parsed_json)
                                        else:
                                            LOG.info("Neither On, Off nor Warm presets selected")
                                        LOG.debug("Matching Linked Area")
                                        self.match_linked_area(area_updated, off_preset, on_preset)
                                    all_channels_off = True #Set Area HB button state if all channels are either on or off
                                    all_channels_on = True
                                    for channel in self.cfg[CONF_AREA][area_updated][CONF_CHANNEL]:
                                        LOG.debug("Channel " + str(channel) + " Preset " + str(self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][channel]["Preset"]))
                                        if str(self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][channel]["Preset"]) != off_preset:
                                            all_channels_off = False
                                        if str(self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][channel]["Preset"]) != on_preset:
                                            all_channels_on = False
                                    if all_channels_off: # Set area HB button to off if all channels are off
                                        pb_parsed_json = {}
                                        pb_parsed_json["name"] = button_json["name"]
                                        pb_parsed_json["service_name"] = button_json["name"]
                                        pb_parsed_json["characteristic"] = "On"
                                        pb_parsed_json["value"] = False
                                        self.outgoing_cb(pb_parsed_json)
                                    elif all_channels_on: # Set area HB button to on if all channels are on
                                        pb_parsed_json = {}
                                        pb_parsed_json["name"] = button_json["name"]
                                        pb_parsed_json["service_name"] = button_json["name"]
                                        pb_parsed_json["characteristic"] = "On"
                                        pb_parsed_json["value"] =True
                                        self.outgoing_cb(pb_parsed_json)
                            if not button_found:
                               LOG.debug("No Homebridge button found for Area Name: " + self.cfg[CONF_AREA][area_updated][CONF_NAME] + " Channel Name: " + self.cfg[CONF_AREA][area_updated][CONF_CHANNEL][str(channel_updated)][CONF_NAME]) 
                        else:
                            LOG.debug("No preset set in channel update")
                    else:
                        LOG.debug("Not a command, ignore")
                else:
                    LOG.debug("No Channel updated")
            else:
                LOG.debug("No channel is defined in config for Area " + str(area_updated) + " " + self.cfg[CONF_AREA][area_updated][CONF_NAME])
        else:
            LOG.info("Area not found in config")
                    
    def update_hb_preset(self, event_data): #Update an area's Homebridge button's state to match the state of its Dynalite area's preset state
        LOG.debug("Update HB Preset " + str(event_data))
        area_updated = None
        for area in self.cfg[CONF_AREA]: #Find area and preset that's been updated and capture its new state
            if area == event_data[CONF_AREA]:
                LOG.debug("Old States " + str(self.cfg[CONF_AREA][area]))
                area_updated = area
                preset_updated = event_data[CONF_PRESET]
                updated_state = event_data["state"]
                other_states = "OFF" if updated_state == "ON" else "ON"
                if str(preset_updated) in self.cfg[CONF_AREA][area][CONF_PRESET]:      
                    for preset in self.cfg[CONF_AREA][area][CONF_PRESET]:
                        if preset == str(preset_updated): #Update config to reflect new states
                            self.cfg[CONF_AREA][area][CONF_PRESET][preset]["state"] = updated_state
                        else:
                            self.cfg[CONF_AREA][area][CONF_PRESET][preset]["state"] = other_states
                    self.match_channel_presets(area_updated, preset_updated)                          
                else:
                    LOG.info("Preset not found in config. Area: " + str(area_updated) + " Preset: " + str(preset_updated))
                    return
        if area_updated != None:
            pb_parsed_json = {}
            pb_parsed_json["name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
            pb_parsed_json["service_name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
            pb_parsed_json["characteristic"] = "On"
            hb_service_found = False
            if "Light" in self.cfg[CONF_AREA][area_updated][CONF_NAME]:
                hb_service_found = True
                target_area, off_preset, on_preset, warm_preset = self.identify_area_presets(self.cfg[CONF_AREA][area_updated][CONF_NAME])
                if warm_preset != None:
                    pb_parsed_json_warm = {}
                    pb_parsed_json_warm["name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                    pb_parsed_json_warm["service_name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                    pb_parsed_json_warm["characteristic"] = "ColorTemperature"
                    if str(preset_updated) == warm_preset:
                        if updated_state == "ON":
                            pb_parsed_json["value"] = True
                            pb_parsed_json_warm["value"] = 400
                            self.outgoing_cb(pb_parsed_json_warm)
                    elif str(preset_updated) != off_preset:
                        if updated_state == "ON":
                            pb_parsed_json["value"] = True
                            pb_parsed_json_warm["value"] = 140
                        self.outgoing_cb(pb_parsed_json_warm)
                    else:
                        pb_parsed_json["value"] = False
                    self.outgoing_cb(pb_parsed_json)
                else:
                    light_state = False
                    if str(preset_updated) != off_preset: #Update Homebridge without catering for a warm preset if the light's not cct
                        if updated_state == "ON":
                            light_state = True
                    pb_parsed_json["value"] = light_state
                    self.outgoing_cb(pb_parsed_json) #Publish non-cct light Homebridge message
                    self.match_linked_hb_channels(area_updated, light_state) # Match Homebridge Light buttons and Dynalite states for Linked Channels                 
            elif "Window" in self.cfg[CONF_AREA][area_updated][CONF_NAME]:
                hb_service_found = True
                LOG.debug("Window")
                pb_parsed_json["service_name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                if self.cfg[CONF_AREA][area_updated][CONF_PRESET][str(preset_updated)][CONF_NAME] == "Open":
                    hb_open_value = 100
                else:
                    hb_open_value = 0
                pb_parsed_json["characteristic"] = "TargetPosition"
                pb_parsed_json["value"] = hb_open_value
                self.outgoing_cb(pb_parsed_json)
                pb_parsed_json1 = {}
                pb_parsed_json1["name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                pb_parsed_json1["service_name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                pb_parsed_json1["characteristic"] = "CurrentPosition"
                pb_parsed_json1["value"] = hb_open_value
                self.outgoing_cb(pb_parsed_json1)
            elif "Shutters" in self.cfg[CONF_AREA][area_updated][CONF_NAME]:
                hb_service_found = True
                LOG.debug("Shutters")
                pb_parsed_json["service_name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                if self.cfg[CONF_AREA][area_updated][CONF_PRESET][str(preset_updated)][CONF_NAME] == "Open":
                    hb_open_value = 100
                else:
                    hb_open_value = 0
                pb_parsed_json["characteristic"] = "TargetPosition"
                pb_parsed_json["value"] = hb_open_value
                self.outgoing_cb(pb_parsed_json)
                pb_parsed_json1 = {}
                pb_parsed_json1["name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                pb_parsed_json1["service_name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                pb_parsed_json1["characteristic"] = "CurrentPosition"
                pb_parsed_json1["value"] = hb_open_value
                self.outgoing_cb(pb_parsed_json1)
            elif "Good Morning" in self.cfg[CONF_AREA][area_updated][CONF_NAME]: #This is a special that uses a dynalite "Good Morning" button to open Main Bedroom shades that respond to the hb_incoming topic
                hb_service_found = True
                LOG.info("Main Bedroom Good Morning Pressed")
                # This was disabled after new Main Bedroom blinds were installed. Now controlled via Control4 and Matter
                #pb_parsed_json = {}
                #pb_parsed_json["name"] = "Main Room Shades"
                #pb_parsed_json["service_name"] = "Day Fresh"
                #if self.cfg[CONF_AREA][area_updated][CONF_PRESET][str(preset_updated)][CONF_NAME] == "On":
                    #hb_open_value = 100
                #else:
                    #hb_open_value = 0
                #pb_parsed_json["characteristic"] = "TargetPosition"
                #pb_parsed_json["value"] = hb_open_value
            else:
                for function in self.hb_switch_functions:
                    if function in self.cfg[CONF_AREA][area_updated][CONF_NAME]:
                        hb_service_found = True
                        LOG.debug("Switch")
                        pb_parsed_json["service_name"] = self.cfg[CONF_AREA][area_updated][CONF_NAME]
                        pb_parsed_json["characteristic"] = "On"
                        if self.cfg[CONF_AREA][area_updated][CONF_PRESET][str(preset_updated)][CONF_NAME] == "On":
                            pb_parsed_json["value"] = True
                        else:
                            pb_parsed_json["value"] = False
                        self.outgoing_cb(pb_parsed_json)               
            if not hb_service_found:
                LOG.info("Homebridge Service not found for Area: " + self.cfg[CONF_AREA][area_updated][CONF_NAME])    
            LOG.debug("New States " + str(self.cfg[CONF_AREA][area_updated]))
        else:
            LOG.info("Updated Area not found in config " + str(event_data)) 

