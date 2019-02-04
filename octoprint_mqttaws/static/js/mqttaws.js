$(function() {
    function MQTTAWSViewModel(parameters) {

        var self = this;

        self.global_settings = parameters[0];
        console.log('aaaa', parameters)

        self.showUserCredentials = ko.observable(false);
        self.showSsl = ko.observable(false);

        self.settings = undefined;
        self.availableProtocols = ko.observableArray(['MQTTv31','MQTTv311']);

        self.onBeforeBinding = function () {
            self.settings = self.global_settings.settings.plugins.mqttaws;

            // show credential options if username is set
            self.showUserCredentials(!!self.settings.broker.username());

            // show SSL/TLS config options if any of the corresponding settings are set
            self.showSsl(!!self.settings.broker.tls && !!self.settings.broker.tls.cacerts && !!self.settings.broker.tls.cacerts())
        };
    }

    ADDITIONAL_VIEWMODELS.push([
        MQTTAWSViewModel,
        ["settingsViewModel"],
        ["#settings_plugin_mqttawsaws"]
    ]);
});
