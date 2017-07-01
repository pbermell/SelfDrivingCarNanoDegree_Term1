import argparse
import base64
#import json
import cv2

import numpy as np
import socketio
#import eventlet
import eventlet.wsgi
#import time
from PIL import Image
#from PIL import ImageOps
from flask import Flask, render_template
from io import BytesIO

from keras.models import model_from_json
from keras.preprocessing.image import ImageDataGenerator, array_to_img, img_to_array

#Fix error with Keras and TensorFlow
import tensorflow as tf
tf.python_control_flow_ops = tf


sio = socketio.Server()
app = Flask(__name__)
model = None
prev_image_array = None

def preprocess_image(img):
    '''
    This method is included here to make images compatible with the CCN
    used for the training
    '''
    # original shape: 160x320x3, input shape for neural net: 66x200x3
    # input shape for Nvidia NN is 66x200x3
    # crop original image to remove sky (50 pixels from top) and car front (20 pixels from bottom)
    # crop to 40x320x3
    new_img = img[50:140,:,:]
    # Apply a Gaussian Blur Filter
    new_img = cv2.GaussianBlur(new_img, (3,3), 0)
    # resize the image to 66x200x3
    new_img = cv2.resize(new_img,(200, 66), interpolation = cv2.INTER_AREA)
    # convert to YUV color space (as nVidia paper suggests)
    # note that images from the simulator come in RGB
    new_img = cv2.cvtColor(new_img, cv2.COLOR_RGB2YUV)
    return new_img

@sio.on('telemetry')
def telemetry(sid, data):
    # The current steering angle of the car
    steering_angle = data["steering_angle"]
    # The current throttle of the car
    throttle = data["throttle"]
    # The current speed of the car
    speed = data["speed"]
    # The current image from the center camera of the car
    imgString = data["image"]
    image = Image.open(BytesIO(base64.b64decode(imgString)))
    image_array = np.asarray(image)
    img = preprocess_image(image_array)
    transformed_image_array = img[None, :, :, :]
    # This model currently assumes that the features of the model are just the images. Feel free to change this.
    steering_angle = float(model.predict(transformed_image_array, batch_size=1))
    # The driving model currently just outputs a constant throttle. Feel free to edit this.
    throttle = 0.2
    if float(speed) < 10:
        throttle = 1
    send_control(steering_angle, throttle)


@sio.on('connect')
def connect(sid, environ):
    print("connect ", sid)
    send_control(0, 0)


def send_control(steering_angle, throttle):
    sio.emit("steer", data={
    'steering_angle': steering_angle.__str__(),
    'throttle': throttle.__str__()
    }, skip_sid=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Remote Driving')
    parser.add_argument('model', type=str,
    help='Path to model definition json. Model weights should be on the same path.')
    args = parser.parse_args()
    with open(args.model, 'r') as jfile:
        # NOTE: if you saved the file by calling json.dump(model.to_json(), ...)
        # then you will have to call:
        #
        #   model = model_from_json(json.loads(jfile.read()))\
        #
        # instead.
        model = model_from_json(jfile.read())
        # model = model_from_json(json.loads(jfile.read()))


    model.compile("adam", "mse")
    weights_file = args.model.replace('json', 'h5')
    model.load_weights(weights_file)

    # wrap Flask application with engineio's middleware
    app = socketio.Middleware(sio, app)

    # deploy as an eventlet WSGI server
    eventlet.wsgi.server(eventlet.listen(('', 4567)), app)