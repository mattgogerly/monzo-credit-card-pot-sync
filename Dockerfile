FROM python:3.13-slim-bookworm

WORKDIR /monzo-credit-card-pot-sync

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY app ./app

CMD [ "flask", "--app" , "app", "run", "--host=0.0.0.0", "--port=1337"]