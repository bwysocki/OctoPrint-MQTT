$(function() {
    function MQTTAWSViewModel(parameters) {

        var self = this;

        self.global_settings = parameters[0];

        self.showUserCredentials = ko.observable(false);
        self.showSsl = ko.observable(false);

        self.settings = undefined;
        self.availableProtocols = ko.observableArray(['WSS']);

        self.onBeforeBinding = function () {
            self.settings = self.global_settings.settings.plugins.mqttaws;
            console.log('aaaa', self.settings)
            // show credential options if username is set
            self.showUserCredentials(!!self.settings.broker.username());

            // show SSL/TLS config options if any of the corresponding settings are set
            self.showSsl(!!self.settings.broker.tls && !!self.settings.broker.tls.cacerts && !!self.settings.broker.tls.cacerts())
        };
    }

    ADDITIONAL_VIEWMODELS.push([
        MQTTAWSViewModel,
        ["settingsViewModel"],
        ["#settings_plugin_mqttaws"]
    ]);
});
