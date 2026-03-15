server {
    listen 127.0.0.1:{{ .port }} default_server;
    listen {{ .interface }}:{{ .port }} default_server;

    include /etc/nginx/includes/server_params.conf;
    include /etc/nginx/includes/proxy_params.conf;

    # Set Home Assistant Ingress header
    proxy_set_header X-HA-Ingress "YES";
    # Forward Authorization (proxy_params.conf clears it; we need it for API/MCP auth)
    proxy_set_header Authorization $http_authorization;

    location / {
        # HA Supervisor / ingress proxy can use .32.1 or .32.2
        allow   172.30.32.1;
        allow   172.30.32.2;
        allow   127.0.0.1;
        deny    all;

        proxy_pass http://esphome;
    }
}
