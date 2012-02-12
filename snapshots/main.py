# -*- coding: utf-8 -*-
import os
import random
import simplejson as json
import string
import time

from httplib2 import Http
from PIL import Image
from urllib import urlencode

from flask import (abort, Flask, jsonify, redirect,
     render_template, request, session, url_for)

import settings

from pymongo import DESCENDING
from pymongo.objectid import ObjectId

from helper import *
from snappy import Snappy

app = Flask(__name__)
app.secret_key = settings.SESSION_SECRET

h = Http()
snappy = Snappy()
PHOTO_THUMB = 250, 250
PHOTO_MEDIUM = 992, 450


@app.route('/', methods=['GET'])
def main():
    """Default landing page"""
    snapshot = snappy.db.photos.find().sort("created_at",
            DESCENDING).limit(1)[0]
    return render_template('index.html',
                           snapshot=snapshot,
                           photo_count=snappy.get_photo_count())
                        

@app.route('/get_snapshot/<page>/<nav>', methods=['GET'])
def get_snapshot(page=1, nav='next'):
    """Get the latest snapshot from pagination/navigation"""
    snapshot = snappy.get_recent(page=page, nav=nav)
    return jsonify({'snapshot':
            {'image_medium': snapshot['image_medium'],
             'id': str(ObjectId(snapshot['_id'])),
             'photo_count': snappy.get_photo_count()}})


@app.route('/your_snapshots', methods=['GET'])
@authenticated
def your_snapshots():
    """Your snapshots"""
    return render_template('your_snapshots.html')


@app.route('/set_email', methods=['POST'])
def set_email():
    """Verify via BrowserID and upon success, set
    the email for the user unless it already
    exists and return the token.
    """
    bid_fields = {'assertion': request.form['bid_assertion'],
                  'audience': settings.DOMAIN}
    headers = {'Content-type': 'application/x-www-form-urlencoded'}
    h.disable_ssl_certificate_validation=True
    resp, content = h.request('https://browserid.org/verify',
                              'POST',
                              body=urlencode(bid_fields),
                              headers=headers)
    bid_data = json.loads(content)
    if bid_data['status'] == 'okay' and bid_data['email']:
        # authentication verified, now get/create the
        # snappy email token
        snappy.get_or_create_email(bid_data['email'])
        session['snapshots_token'] = snappy.token
        session['snapshots_email'] = bid_data['email']
    return redirect(url_for('your_snapshots'))


@app.route('/upload', methods=['GET', 'POST'])
@authenticated
@csrf_protect
def upload():
    """Upload a photo and save two versions - the original, medium
    and the thumb.
    """
    if request.method == 'POST':
        filename = str(int(time.time()))
        request.files['photo'].save(os.path.join('tmp/', filename))

        thumb = Image.open(os.path.join('tmp/', filename))
        thumb.thumbnail(PHOTO_THUMB, Image.BICUBIC)
        thumb.save('tmp/' + filename + '_thumb', 'PNG')

        medium = Image.open(os.path.join('tmp/', filename))
        medium.thumbnail(PHOTO_MEDIUM, Image.BICUBIC)
        medium.save('tmp/' + filename + '_medium', 'PNG')

        large = Image.open(os.path.join('tmp/', filename))
        large.save('tmp/' + filename + '_original', 'PNG')
        snapshot = snappy.upload(request.form['description'],
                                 filename,
                                 session.get('snapshots_token'))
        return redirect(url_for('snapshot', id=snapshot['_id']))
    else:
        return render_template('upload.html')


@app.route('/snapshot/<id>', methods=['GET'])
def snapshot(id=None):
    """Your snapshot."""
    snapshot = snappy.get_image(id)
    return render_template('snapshot.html', snapshot=snapshot)


@app.route('/snapshot/edit/<id>', methods=['GET', 'POST'])
@authenticated
@csrf_protect
def edit(id=None):
    """Edit or update an existing snapshot."""
    snapshot = snappy.get_image_by_user(id, session['snapshots_token'])

    if request.method == 'POST':
        snappy.update_description(id, request.form['description'])
        return redirect(url_for('snapshot', id=snapshot['_id']))
    else:
        return render_template('edit.html', snapshot=snapshot)


@app.route('/snapshot/delete/<id>', methods=['GET'])
@authenticated
def delete(id=None):
    """Delete an existing snapshot."""
    snappy.delete_image(id, session['snapshots_token'])
    return redirect(url_for('main'))


@app.route('/logout', methods=['GET'])
def logout():
    """Log the user out"""
    session['snapshots_email'] = None
    session['snapshots_token'] = None
    return redirect(url_for('main'))


def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = ''.join(
                random.choice(string.ascii_lowercase + string.digits) for x in range(30))

    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token


if __name__ == '__main__':
    app.debug = settings.DEBUG
    app.env = 'dev'
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
