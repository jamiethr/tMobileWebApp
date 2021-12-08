# dockerfile that creates a container for the organizer tool's server
FROM python:3.7-alpine
WORKDIR /code
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Install python/pip
# ENV PYTHONUNBUFFERED=1
# RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
# RUN python3 -m ensurepip
# RUN pip3 install --no-cache --upgrade pip setuptools

RUN apk add --update py-pip
RUN apk add build-base python3-dev py-pip jpeg-dev zlib-dev
ENV LIBRARY_PATH=/lib:/usr/lib
RUN pip install Pillow
RUN pip install docker

# debug thing: install mysql to test connections, etc.
RUN apk add mysql mysql-client mariadb-common

RUN apk add --no-cache gcc musl-dev linux-headers
RUN apk add --no-cache libffi-dev
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
EXPOSE 5000
COPY . .
# CMD ["flask", "run"]
CMD ["python", "server.py"]