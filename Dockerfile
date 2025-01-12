FROM python:3.13-slim-bookworm

WORKDIR /monzo-credit-card-pot-sync

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY app .

CMD [ "flask", "--app" , "app", "run", "--port=1337"]