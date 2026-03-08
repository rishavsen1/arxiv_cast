from flask import Flask
import psutil
import os

app = Flask(__name__)

def get_temp():
	# Reads Pi's internal temperature
	temp = os.popen("vcgencmd measure_temp").readline()
	return temp.replace("temp=","").replace("'C\n","")

@app.route('/')
def index():
	cpu = psutil.cpu_percent(interval=1)
	ram = psutil.virtual_memory().percent
	temp = get_temp()

	return f"""
	<html>
	<head>meta http-equiv="refresh" content="60"><\head>
	<body style="font-family:sans-serif; text-align: center; passing-top:50px;">
		<h1>Raspberry Pi Health Status</h1>
	        <p><strong>CPU Usage:</strong> {cpu}%</p>
	        <p><strong>RAM Usage:</strong> {ram}%</p>
	        <p><strong>CPU Temp:</strong> {temp}°C</p>
	        <p><i>Auto-refreshing every 60 seconds...</i></p>
	</body>
	</html>
	"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

