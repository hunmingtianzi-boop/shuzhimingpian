FROM nginx:1.31.2-alpine3.23
COPY infra/gateway/nginx.conf /etc/nginx/nginx.conf
RUN chmod 0644 /etc/nginx/nginx.conf
USER nginx
EXPOSE 8080 8081
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD wget -q -O - http://127.0.0.1:8080/gateway-health || exit 1
