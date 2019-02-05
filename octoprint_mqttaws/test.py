import json
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import time

host = 'a9tg1a03ro09m-ats.iot.eu-central-1.amazonaws.com'
rootCAPath = './AmazonRootCA1.pem'
port = 443
clientId = 'TODO'
topic = 'abcmqtt'

# Custom MQTT message callback
def customCallback(client, userdata, message):
    print("Received a new message: ")
    print(message.payload)
    print("from topic: ")
    print(message.topic)
    print("--------------\n\n")

myAWSIoTMQTTClient = AWSIoTMQTTClient(clientId, useWebsocket=True)
myAWSIoTMQTTClient.configureEndpoint(host, port)
myAWSIoTMQTTClient.configureCredentials(rootCAPath)

# AWSIoTMQTTClient connection configuration
myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec

# Connect and subscribe to AWS IoT
myAWSIoTMQTTClient.connect()

myAWSIoTMQTTClient.subscribe(topic, 1, customCallback)

message = {}
message['message'] = 'abcada'
messageJson = json.dumps(message)
myAWSIoTMQTTClient.publish(topic, messageJson, 1)

a = {"a":1}

print a.get('a')
time.sleep(1)
