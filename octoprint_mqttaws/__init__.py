# coding=utf-8
from __future__ import absolute_import

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

import json
import time
from collections import deque
import os
import socket
import socks

import octoprint.plugin

from octoprint.events import Events
from octoprint.util import dict_minimal_mergediff


class MqttAWSPlugin(
        octoprint.plugin.SettingsPlugin, octoprint.plugin.StartupPlugin,
        octoprint.plugin.ShutdownPlugin, octoprint.plugin.EventHandlerPlugin,
        octoprint.plugin.ProgressPlugin, octoprint.plugin.TemplatePlugin,
        octoprint.plugin.AssetPlugin, octoprint.printer.PrinterCallback):

    EVENT_CLASS_TO_EVENT_LIST = dict(
        server=(
            Events.STARTUP, Events.SHUTDOWN, Events.CLIENT_OPENED,
            Events.CLIENT_CLOSED, Events.CONNECTIVITY_CHANGED
        ),
        comm=(
            Events.CONNECTING, Events.CONNECTED, Events.DISCONNECTING,
            Events.DISCONNECTED, Events.ERROR, Events.PRINTER_STATE_CHANGED
        ),
        files=(
            Events.UPLOAD, Events.FILE_ADDED, Events.FILE_REMOVED,
            Events.FOLDER_ADDED, Events.FOLDER_REMOVED, Events.UPDATED_FILES,
            Events.METADATA_ANALYSIS_STARTED,
            Events.METADATA_ANALYSIS_FINISHED, Events.FILE_SELECTED,
            Events.FILE_DESELECTED, Events.TRANSFER_STARTED,
            Events.TRANSFER_FAILED, Events.TRANSFER_DONE
        ),
        printjob=(
            Events.PRINT_STARTED, Events.PRINT_FAILED, Events.PRINT_DONE,
            Events.PRINT_CANCELLED, Events.PRINT_PAUSED, Events.PRINT_RESUMED
        ),
        gcode=(
            Events.POWER_ON, Events.POWER_OFF, Events.HOME, Events.Z_CHANGE,
            Events.DWELL, Events.WAITING, Events.COOLING, Events.ALERT,
            Events.CONVEYOR, Events.EJECT, Events.E_STOP,
            Events.POSITION_UPDATE, Events.TOOL_CHANGE
        ),
        timelapse=(
            Events.CAPTURE_START, Events.CAPTURE_FAILED, Events.CAPTURE_DONE,
            Events.MOVIE_RENDERING, Events.MOVIE_FAILED, Events.MOVIE_FAILED
        ),
        slicing=(
            Events.SLICING_STARTED, Events.SLICING_DONE,
            Events.SLICING_CANCELLED, Events.SLICING_FAILED,
            Events.SLICING_PROFILE_ADDED, Events.SLICING_PROFILE_DELETED,
            Events.SLICING_PROFILE_MODIFIED
        ),
        settings=(Events.SETTINGS_UPDATED,)
    )

    LWT_CONNECTED = "connected"
    LWT_DISCONNECTED = "disconnected"

    def __init__(self):
        self._mqtt = None
        self._mqtt_connected = False

        self._mqtt_subscriptions = []

        self._mqtt_publish_queue = deque()
        self._mqtt_subscribe_queue = deque()

        self.lastTemp = {}
        self._proxySocket = None
        self._proxySocksSocket = None

    def initialize(self):
        self._printer.register_callback(self)

        if self._settings.get(["broker", "url"]) is None:
            self._logger.error(
                "No broker URL defined, MQTT plugin won't be able to work"
            )
            return False

    # ~~ TemplatePlugin API

    def get_template_configs(self):
        return [dict(type="settings", name="MQTTAWS")]

    # ~~ AssetPlugin API

    def get_assets(self):
        return dict(js=["js/mqttaws.js"])

    # ~~ StartupPlugin API

    def on_startup(self, host, port):
        self.mqtt_connect()

    # ~~ ShutdownPlugin API

    def on_shutdown(self):
        self.mqtt_disconnect(force=True)

    # ~~ SettingsPlugin API

    def get_settings_defaults(self):
        return dict(
            broker=dict(
                url=None,
                port=1883,
                username=None,
                password=None,
                keepalive=60,
                tls=dict(),
                tls_insecure=False,
                protocol="MQTTv31",
                awsaccesskey='',
                secretawsaccesskey=''
            ),
            publish=dict(
                baseTopic="octoprint/",
                eventTopic="event/{event}",
                eventActive=True,
                printerData=False,
                events=dict(
                    server=True,
                    comm=True,
                    files=True,
                    printjob=True,
                    gcode=True,
                    timelapse=True,
                    slicing=True,
                    settings=True,
                    unclassified=True
                ),
                progressTopic="progress/{progress}",
                progressActive=True,
                temperatureTopic="temperature/{temp}",
                temperatureActive=True,
                temperatureThreshold=0.1,
                lwTopic="mqtt",
                lwActive=True
            )
        )

    def on_settings_save(self, data):
        old_broker_data = self._settings.get(["broker"])
        old_lw_active = self._settings.get_boolean(["publish", "lwActive"])
        old_lw_topic = self._get_topic("lw")

        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

        new_broker_data = self._settings.get(["broker"])
        new_lw_active = self._settings.get_boolean(["publish", "lwActive"])
        new_lw_topic = self._get_topic("lw")

        broker_diff = dict_minimal_mergediff(old_broker_data, new_broker_data)
        lw_diff = dict_minimal_mergediff(
            dict(lw_active=old_lw_active, lw_topic=old_lw_topic),
            dict(lw_active=new_lw_active, lw_topic=new_lw_topic)
        )
        if len(broker_diff) or len(lw_diff):
            # something changed
            self._logger.info(
                "Settings changed (broker_diff={!r}, lw_diff={!r}), "
                "reconnecting to broker".format(broker_diff, lw_diff)
            )
            self.mqtt_disconnect(
                force=True, incl_lwt=old_lw_active, lwt=old_lw_topic
            )
            self.mqtt_connect()

    # ~~ EventHandlerPlugin API

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:
            self.on_print_progress(payload["origin"], payload["path"], 0)
        elif event == Events.PRINT_DONE:
            self.on_print_progress(payload["origin"], payload["path"], 100)
        elif event == Events.FILE_SELECTED:
            self.on_print_progress(payload["origin"], payload["path"], 0)
        elif event == Events.FILE_DESELECTED:
            self.on_print_progress("", "", 0)

        topic = self._get_topic("event")

        if topic:
            if self._is_event_active(event):
                if payload is None:
                    data = dict()
                else:
                    data = dict(payload)
                data["_event"] = event
                self.mqtt_publish_with_timestamp(
                    topic.format(event=event), data
                )

    # ~~ ProgressPlugin API

    def on_print_progress(self, storage, path, progress):
        topic = self._get_topic("progress")

        if topic:
            data = dict(location=storage, path=path, progress=progress)

            if self._settings.get_boolean(["publish", "printerData"]):
                data['printer_data'] = self._printer.get_current_data()

            self.mqtt_publish_with_timestamp(
                topic.format(progress="printing"), data, retained=True
            )

    def on_slicing_progress(
            self, slicer, source_location, source_path, destination_location,
            destination_path, progress
    ):
        topic = self._get_topic("progress")

        if topic:
            data = dict(
                slicer=slicer,
                source_location=source_location,
                source_path=source_path,
                destination_location=destination_location,
                destination_path=destination_path,
                progress=progress
            )
            self.mqtt_publish_with_timestamp(
                topic.format(progress="slicing"), data, retained=True
            )

    # ~~ PrinterCallback

    def on_printer_add_temperature(self, data):
        topic = self._get_topic("temperature")
        threshold = self._settings.get_float([
            "publish", "temperatureThreshold"
        ])

        if topic:
            for key, value in data.items():
                if key == "time":
                    continue

                if (key not in self.lastTemp
                        or abs(value["actual"] - self.lastTemp[key]["actual"])
                        >= threshold
                        or value["target"] != self.lastTemp[key]["target"]):
                    # unknown key,
                    # new actual or new target -> update mqtt topic!
                    dataset = dict(
                        actual=value["actual"], target=value["target"]
                    )
                    self.mqtt_publish_with_timestamp(
                        topic.format(temp=key),
                        dataset,
                        retained=True,
                        allow_queueing=True,
                        timestamp=data["time"]
                    )
                    self.lastTemp.update({key: data[key]})

    # ~~ Softwareupdate hook

    def get_update_information(self):
        return dict(
            mqtt=dict(
                displayName=self._plugin_name,
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="OctoPrint",
                repo="OctoPrint-MQTT",
                current=self._plugin_version,

                # update method: pip
                pip=(
                    "https://github.com/bwysocki/OctoPrint-MQTT/"
                    "archive/{target_version}.zip"
                )
            )
        )

    # ~~ helpers

    def logCallback(self, client, userdata, message):
        self._logger.info(
            'Incomming message {message} from topic {topic}'.format(
                message=message.payload, topic=message.topic
            )
        )

    def mqtt_connect(self):
        if not self._mqtt_connected:
            accessKey = self._settings.get(["broker", "awsaccesskey"])
            secretAccessKey = self._settings.get([
                "broker", "secretawsaccesskey"
            ])

            if (not accessKey or not secretAccessKey):
                return

            os.environ["AWS_ACCESS_KEY_ID"] = accessKey
            os.environ["AWS_SECRET_ACCESS_KEY"] = secretAccessKey

            broker_tls = self._settings.get(["broker", "tls"], asdict=True)
            host = self._settings.get(["broker", "url"])
            rootCAPath = broker_tls.get('ca_certs')
            port = 443
            clientId = self._settings.get(["publish", "baseTopic"])

            myAWSIoTMQTTClient = AWSIoTMQTTClient(clientId, useWebsocket=True)

            env = os.environ.copy()
            proxy = env.get("http_proxy", None)
            self._logger.info(env)
            self._logger.info("Checking proxy: {proxy}".format(proxy=proxy))
            if proxy:
                proxyEnv = proxy.replace("http://", "").replace("https://", "")
                proxy = proxyEnv.strip().split(":")
                proxyHost = str(proxy[0])
                proxyPort = int(proxy[1])
                self._logger.info(
                    'MQTTAWS started with proxy: {proxyHost}:{proxyPort}'
                    .format(proxyPort=proxyPort, proxyHost=proxyHost)
                )
                socks.setdefaultproxy(
                    socks.PROXY_TYPE_HTTP, proxyHost, proxyPort
                )
                self._proxySocket = socket.socket
                self._proxySocksSocket = socks.socksocket
                socket.socket = socks.socksocket
                os.environ['NO_PROXY'] = 'localhost'

            myAWSIoTMQTTClient.configureEndpoint(host, port)
            myAWSIoTMQTTClient.configureCredentials(rootCAPath)

            # AWSIoTMQTTClient connection configuration
            myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 3200, 20)
            myAWSIoTMQTTClient.configureOfflinePublishQueueing(
                -1
            )  # Infinite offline Publish queueing
            myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
            myAWSIoTMQTTClient.configureConnectDisconnectTimeout(100)  # 10 sec
            myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec

            myAWSIoTMQTTClient.onOffline = self._on_mqtt_disconnect
            myAWSIoTMQTTClient.onOnline = self._on_mqtt_connect
            myAWSIoTMQTTClient.onMessage = self._on_mqtt_message

            try:
              myAWSIoTMQTTClient.connect()
              self._mqtt = myAWSIoTMQTTClient
            except:
              self.mqtt_connect()


    def mqtt_disconnect(self, force=False, incl_lwt=True, lwt=None):
        if self._mqtt is None:
            return

        if incl_lwt:
            if lwt is None:
                lwt = self._get_topic("lw")
            if lwt:
                self._mqtt.publish(
                    topic=lwt, payload=self.LWT_DISCONNECTED, QoS=1
                )

        self._mqtt.disconnect()

    def mqtt_publish_with_timestamp(
            self,
            topic,
            payload,
            retained=False,
            qos=0,
            allow_queueing=False,
            timestamp=None
    ):
        if not payload:
            payload = dict()
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")

        if timestamp is None:
            timestamp = time.time()
        payload["_timestamp"] = int(timestamp)
        return self.mqtt_publish(
            topic,
            payload,
            retained=retained,
            qos=qos,
            allow_queueing=allow_queueing
        )

    def mqtt_publish(
            self, topic, payload, retained=False, qos=0, allow_queueing=False
    ):
        if not isinstance(payload, basestring):
            payload = json.dumps(payload)
        if not self._mqtt_connected:
            if allow_queueing:
                self._logger.debug(
                    "Not connected, enqueuing message: {topic} - {payload}"
                    .format(**locals())
                )
                self._mqtt_publish_queue.append(
                    (topic, payload, retained, qos)
                )
                return True
            else:
                return False
        self._mqtt.publish(topic, payload=payload, QoS=qos)
        self._logger.info(
            "Sent message: {topic} - {payload}".format(**locals())
        )
        return True

    def mqtt_subscribe(self, topic, callback, args=None, kwargs=None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = dict()
        self._mqtt_subscriptions.append((topic, callback, args, kwargs))

        if not self._mqtt_connected:
            self._mqtt_subscribe_queue.append(topic)
        else:
            self._mqtt.subscribe(topic, 1, self.logCallback)

    def mqtt_unsubscribe(self, callback, topic=None):
        subbed_topics = [
            subbed_topic
            for subbed_topic, subbed_callback, _, _ in self._mqtt_subscriptions
            if callback == subbed_callback and
            (topic is None or topic == subbed_topic)
        ]

        def remove_sub(entry):
            subbed_topic, subbed_callback, _, _ = entry
            return not (
                callback == subbed_callback and
                (topic is None or subbed_topic == topic)
            )

        self._mqtt_subscriptions = filter(remove_sub, self._mqtt_subscriptions)

        if self._mqtt_connected and subbed_topics:
            self._mqtt.unsubscribe(*subbed_topics)

    # ~~ mqtt client callbacks

    def _on_mqtt_connect(self):
        self._logger.info("Printer gets connection")
        # noqa if self._mqtt_publish_queue:
        # noqa     try:
        # noqa         while True:
        # noqa             topic, payload, retained, qos = self._mqtt_publish_queue.popleft()
        # noqa             self._mqtt.publish(topic, payload=payload, QoS=qos)
        # noqa     except IndexError:
        # noqa         # that's ok, queue is just empty
        # noqa         pass
        # noqa subbed_topics = list(map(lambda t: (t, 0), {topic for topic, _, _, _ in self._mqtt_subscriptions}))
        # noqa if subbed_topics:
        # noqa     self._mqtt.subscribe(subbed_topics, 1, self.logCallback)
        self._mqtt_connected = True
        self.mqtt_connect()

    def _on_mqtt_disconnect(self):
        self._logger.info("Printer lost connection")
        self._mqtt_connected = False

    def _on_mqtt_message(self, msg):
        from paho.mqtt.client import topic_matches_sub
        for subscription in self._mqtt_subscriptions:
            topic, callback, args, kwargs = subscription
            if topic_matches_sub(topic, msg.topic):
                args = [msg.topic, msg.payload] + args
                kwargs.update(dict(client=None, userdata=None, message=msg))
                try:
                    if (self._proxySocket):
                        socket.socket = self._proxySocket
                    callback(*args, **kwargs)
                    if (self._proxySocksSocket):
                        socket.socket = self._proxySocksSocket
                except Exception:
                    self._logger.exception("Error while calling mqtt callback")

    def _get_topic(self, topic_type):
        sub_topic = self._settings.get(["publish", topic_type + "Topic"])
        topic_active = self._settings.get(["publish", topic_type + "Active"])
        if not sub_topic or not topic_active:
            return None

        return self._settings.get(["publish", "baseTopic"]) + sub_topic

    def _is_event_active(self, event):
        for event_class, events in self.EVENT_CLASS_TO_EVENT_LIST.items():
            if event in events:
                return self._settings.get_boolean([
                    "publish", "events", event_class
                ])
        return self._settings.get_boolean([
            "publish", "events", "unclassified"
        ])


__plugin_name__ = "MQTTAWS"


def __plugin_load__():
    plugin = MqttAWSPlugin()

    global __plugin_helpers__
    __plugin_helpers__ = dict(
        mqttaws_publish=plugin.mqtt_publish,
        mqttaws_publish_with_timestamp=plugin.mqtt_publish_with_timestamp,
        mqttaws_subscribe=plugin.mqtt_subscribe,
        mqttaws_unsubscribe=plugin.mqtt_unsubscribe
    )

    global __plugin_implementation__
    __plugin_implementation__ = plugin

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config":
        __plugin_implementation__.get_update_information
    }
