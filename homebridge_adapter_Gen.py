#!/usr/bin/env python3
#Northcliff Homebridge Adapter - Version 1.0 - Gen
import logging

LOG = logging.getLogger(__name__)

class HomebridgeAdapter:
    def __init__(self, controller):
        self.controller = controller
        
    def handle_message(self, parsed_json):
        """
        Accepts decoded Homebridge JSON.
        Returns optional response JSON (or None)
        """
        
        if not all(k in parsed_json for k in ("service_type", "characteristic", "name")):
            LOG.debug("Ignoring incomplete Homebridge message: %s", parsed_json)
            return None
        
        service = parsed_json["service_type"]
        characteristic = parsed_json["characteristic"]
        
        # ---- Window ----
        if service == "Window" and characteristic == "TargetPosition":
            return self.controller.operate_window(parsed_json)
        
        # ---- Light ----
        if service == "Lightbulb":
            return self.controller.operate_light(
                parsed_json,
                switch_entire_area=False,
                match_linked_area=True
            )
        
        # ---- Switch ----
        if service == "Switch":
            return self.controller.operate_switch(parsed_json)
        
        # ---- Shutters Special Case ----
        if "Shutters" in parsed_json["name"] and characteristic == "Target Position":
            return self.controller.operate_window(parsed_json)
        
        # ---- Main Room Shades Special Case
        if parsed_json["name"] == "Main Room Shades":
            if parsed_json["value"] == 0:
                #This is a special that uses a dynalite "Good Morning" button to open blinds that respond to the hb_incoming topic.
                #It resets the Good Morning button when any blind is closed
                LOG.info("Resetting Main Bedroom Good Morning button")
                self.dyn.devices[CONF_AREA][148].presetOn(4)
            elif parsed_json["value"] == 100:
                #This is a special that uses a dynalite "Good Morning" button to open blinds that respond to the hb_incoming topic.
                #It sets the Good Morning button when any Main Bedroom window shade is opened
                LOG.info("Setting Main Bedroom Good Morning button")
                self.dyn.devices[CONF_AREA][148].presetOn(1)
        return None
    
        
          
        
        
                   