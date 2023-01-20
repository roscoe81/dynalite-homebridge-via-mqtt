# dynalite-homebridge-via-mqtt
A prototype bridge between Homebridge and Dynalite via mqtt commands. It uses the [Python Dynalite Library](https://github.com/troykelly/python-dynalite) and [Homebridge mqtt plug-in](https://github.com/cflurin/homebridge-mqtt). It currently only supports a limited number of accessory types (lights, windows and switches).

## Configuration
Set up by populating the cfg dictionary. The code has an example that can be modified to suit your dynalite setup with areas, names, presets and channels. You will need to configure the IP address and port number of your RS485 to IP gateway and the IP address of your mqtt broker.

## License
This project is licensed under the MIT License - see the LICENSE.md file for details
