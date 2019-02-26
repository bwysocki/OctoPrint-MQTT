# coding=utf-8
from setuptools import setup

try:
    import octoprint_setuptools
except Exception:
    print(
        "Could not import OctoPrint's setuptools, "
        "are you sure you are running that under the same python installation "
        "that OctoPrint is installed under?"
    )
    import sys
    sys.exit(-1)

# The plugin's identifier, has to be unique
plugin_identifier = "mqttaws"

# The plugin's python package, should be "octoprint_<plugin identifier>",
# has to be unique
plugin_package = "octoprint_mqttaws"

# The plugin's human readable name.
# Can be overwritten within OctoPrint's internal data via __plugin_name__
# in the plugin module
plugin_name = "OctoPrint-MQTTAWS"

# The plugin's version.
# Can be overwritten within OctoPrint's internal data via __plugin_version__
# in the plugin module
plugin_version = "0.8.1"

# The plugin's description. Can be overwritten within OctoPrint's
# internal data via __plugin_description__ in the plugin module
plugin_description = (
    "An OctoPrint Plugin that adds to OctoPrint support "
    "for MQTT with AWS IOT brokers."
)

# The plugin's author.
# Can be overwritten within OctoPrint's internal data via
# __plugin_author__ in the plugin module
plugin_author = "Gina H�u�ge Bartosz Wysocki"

# The plugin's author's mail address.
plugin_author_email = "gina@octoprint.org"

# The plugin's homepage URL.
# Can be overwritten within OctoPrint's internal data via __plugin_url__
# in the plugin module
plugin_url = "https://github.com/bwysocki/OctoPrint-MQTT"

# The plugin's license.
# Can be overwritten within OctoPrint's internal data via __plugin_license__
# in the plugin module
plugin_license = "AGPLv3"

# Any additional requirements besides OctoPrint should be listed here
plugin_requires = [
    "OctoPrint>=1.3.5",
    "paho-mqtt",
    "AWSIoTPythonSDK",
    "PySocks",
    "httplib2",
    "requests"
]

extras_require = {
    'dev': [
        'pre-commit>=1.14.4,<1.15',
        'flake8==3.7.5',
        'yapf==0.26.0',
    ]
}

setup_parameters = octoprint_setuptools.create_plugin_setup_parameters(
    identifier=plugin_identifier,
    package=plugin_package,
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    mail=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    requires=plugin_requires,
    extra_requires=extras_require,
)

setup(**setup_parameters)
