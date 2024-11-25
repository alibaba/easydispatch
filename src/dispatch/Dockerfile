FROM easydispatch-container-reg-registry.ap-southeast-1.cr.aliyuncs.com/easydispatch-yun-test/easydispatch-backend:latest

COPY ./ /usr/local/lib/python3.9/site-packages/dispatch/

EXPOSE 8000
VOLUME /var/lib/dispatch/files

ENTRYPOINT ["dispatch"]
CMD ["server", "start", "dispatch.main:app", "--host=0.0.0.0"]

