FROM python:3.13-slim-bookworm

WORKDIR /monzo-credit-card-pot-sync

COPY requirements.txt wsgi.py ./

RUN pip3 install -r requirements.txt

COPY app ./app

CMD ["gunicorn", "--bind", "0.0.0.0:1337", "wsgi:app"]