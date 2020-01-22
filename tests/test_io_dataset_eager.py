# Copyright 2018 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License.  You may obtain a copy of
# the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations under
# the License.
# ==============================================================================
"""Test IODataset"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import sys
import time
import shutil
import tempfile
import numpy as np
import pytest

import tensorflow as tf
import tensorflow_io as tfio

def element_equal(x, y):
  if not isinstance(x, tuple):
    return np.array_equal(x, y)
  for a, b in zip(list(x), list(y)):
    if not np.array_equal(a, b):
      return False
  return True

def element_slice(e, i, j):
  entries = e[i:j]
  if not isinstance(entries[0], tuple):
    return entries
  elements = [[] for _ in entries[0]]
  for entry in entries:
    for k, v in enumerate(list(entry)):
      elements[k].append(v)
  return [np.stack(element) for element in elements]

@pytest.fixture(name="fixture_lookup")
def fixture_lookup_func(request):
  def _fixture_lookup(name):
    return request.getfixturevalue(name)
  return _fixture_lookup

@pytest.fixture(name="mnist")
def fixture_mnist():
  """fixture_mnist"""
  mnist_filename = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_mnist",
      "mnist.npz")
  with np.load(mnist_filename) as f:
    x_test, y_test = f['x_test'], f['y_test']

  image_filename = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_mnist",
      "t10k-images-idx3-ubyte")
  label_filename = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_mnist",
      "t10k-labels-idx1-ubyte")

  # no need to test all, just take first 1000

  args = tf.stack([image_filename, label_filename])
  def func(e):
    image_filename, label_filename = e[0], e[1]
    return tfio.IODataset.from_mnist(
        images=image_filename, labels=label_filename).take(1000)
  expected = [(x_test[i], y_test[i]) for i in range(1000)]

  return args, func, expected

@pytest.fixture(name="mnist_gz")
def fixture_mnist_gz():
  """fixture_mnist_gz"""
  mnist_filename = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_mnist",
      "mnist.npz")
  with np.load(mnist_filename) as f:
    x_test, y_test = f['x_test'], f['y_test']

  image_filename = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_mnist",
      "t10k-images-idx3-ubyte.gz")
  label_filename = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_mnist",
      "t10k-labels-idx1-ubyte.gz")

  # no need to test all, just take first 1000

  args = tf.stack([image_filename, label_filename])
  def func(e):
    image_filename, label_filename = e[0], e[1]
    return tfio.IODataset.from_mnist(
        images=image_filename, labels=label_filename).take(1000)
  expected = [(x_test[i], y_test[i]) for i in range(1000)]

  return args, func, expected

@pytest.fixture(name="lmdb")
def fixture_lmdb(request):
  """fixture_lmdb"""
  path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)), "test_lmdb", "data.mdb")
  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "data.mdb")
  shutil.copy(path, filename)

  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  args = filename
  func = tfio.IODataset.from_lmdb
  expected = [
      (str(i).encode(), str(chr(ord("a") + i)).encode()) for i in range(10)]

  return args, func, expected

@pytest.fixture(name="pubsub")
def fixture_pubsub(request):
  """fixture_pubsub"""
  from google.cloud import pubsub_v1 # pylint: disable=import-outside-toplevel

  channel = "e{}e".format(time.time())

  os.environ['PUBSUB_EMULATOR_HOST'] = 'localhost:8085'
  publisher = pubsub_v1.PublisherClient()
  topic_path = publisher.topic_path(
      "pubsub-project", "pubsub_topic_"+channel)
  publisher.create_topic(topic_path)
  # print('Topic created: {}'.format(topic))
  subscriber = pubsub_v1.SubscriberClient()
  subscription_path = subscriber.subscription_path(
      "pubsub-project",
      "pubsub_subscription_{}".format(channel))
  subscription = subscriber.create_subscription(
      subscription_path, topic_path, retain_acked_messages=True)
  print('Subscription created: {}'.format(subscription))
  for n in range(0, 10):
    data_v = u'Message number {}'.format(n)
    # Data must be a bytestring
    data_v = data_v.encode('utf-8')
    # When you publish a message, the client returns a future.
    future = publisher.publish(topic_path, data=data_v)
    print('Published {} of message ID {}.'.format(data_v, future.result()))
  print('Published messages.')

  def fin():
    subscription_path = subscriber.subscription_path(
        "pubsub-project",
        "pubsub_subscription_{}".format(channel))
    subscriber.delete_subscription(subscription_path)
    print('Subscription {} deleted.'.format(subscription_path))
  request.addfinalizer(fin)

  args = ("projects/pubsub-project/"
          "subscriptions/pubsub_subscription_{}".format(channel))
  def func(q):
    v = tfio.experimental.IODataset.stream().from_pubsub(
        q, endpoint="http://localhost:8085", timeout=5000)
    v = v.map(lambda e: e.data)
    return v
  expected = ['Message number {}'.format(n).encode() for n in range(10)]

  return args, func, expected

@pytest.fixture(name="grpc")
def fixture_grpc():
  """fixture_grpc"""

  data = [[i, i+1, i+2] for i in range(0, 5000)]

  args = np.asarray(data)
  func = lambda e: tfio.experimental.IODataset.stream().from_grpc_numpy(e)
  expected = data

  return args, func, expected

@pytest.fixture(name="prometheus")
def fixture_prometheus():
  """fixture_prometheus"""

  offset = int(round(time.time() * 1000))
  args = "coredns_dns_request_count_total"
  def func(q):
    v = tfio.experimental.IODataset.from_prometheus(q, 5, offset=offset)
    v = v.map(lambda timestamp, value: (
        timestamp,
        value['coredns']['localhost:9153']['coredns_dns_request_count_total']))
    v = v.map(lambda timestamp, value: (
        tf.stack([tf.cast(timestamp - offset, tf.float64), value])))
    return v
  expected = [[np.float64(i), 6.0] for i in range(-5000, 0, 1000)]

  return args, func, expected

@pytest.fixture(name="prometheus_graph")
def fixture_prometheus_graph():
  """fixture_prometheus_graph"""

  offset = int(round(time.time() * 1000))
  args = "up"
  def func(q):
    v = tfio.experimental.IODataset.from_prometheus(
        q, 5, offset=offset,
        spec={
            'coredns': {
                'localhost:9153': {
                    'up': tf.TensorSpec([], tf.float64),
                },
            },
            'prometheus': {
                'localhost:9090': {
                    'up': tf.TensorSpec([], tf.float64),
                },
            },
        })
    v = v.map(lambda _, value: (
        value['coredns']['localhost:9153']['up'],
        value['prometheus']['localhost:9090']['up']))
    return v
  expected = [[1.0, 1.0] for _ in range(0, 5000, 1000)]

  return args, func, expected

# prometheus scrape stream never repeat so
# we only test basic operation to make sure it could
# be used in inference
@pytest.fixture(name="prometheus_scrape")
def fixture_prometheus_scrape():
  """fixture_prometheus_scrape"""

  timestamp = int(round(time.time() * 1000))
  args = "coredns_dns_request_count_total"
  def func(q):
    v = tfio.experimental.IODataset.stream().from_prometheus_scrape(
        q, "http://localhost:9153/metrics").take(5)
    v = v.map(lambda v: tf.stack([v.value, tf.cast(v.timestamp > timestamp, tf.float64)]))
    return v
  expected = [[6.0, 1.0] for _ in range(5)]

  return args, func, expected

@pytest.fixture(name="kinesis")
def fixture_kinesis(request):
  """fixture_kinesis"""
  import boto3 # pylint: disable=import-outside-toplevel

  val = [("D" + str(i)) for i in range(10)]
  key = [("TensorFlow" + str(i)) for i in range(10)]

  os.environ['AWS_ACCESS_KEY_ID'] = 'ACCESS_KEY'
  os.environ['AWS_SECRET_ACCESS_KEY'] = 'SECRET_KEY'
  os.environ['KINESIS_USE_HTTPS'] = '0'
  os.environ['KINESIS_ENDPOINT'] = 'localhost:4568'

  client = boto3.client(
      'kinesis', region_name='us-east-1',
      endpoint_url='http://localhost:4568')

  # Setup the Kinesis with 1 shard.
  stream_name = "kinesis_e{}e".format(time.time())
  client.create_stream(StreamName=stream_name, ShardCount=1)
  # Wait until stream exists, default is 10 * 18 seconds.
  client.get_waiter('stream_exists').wait(StreamName=stream_name)
  for v, k in zip(val, key):
    client.put_record(StreamName=stream_name, Data=v, PartitionKey=k)
  def fin():
    client.delete_stream(StreamName=stream_name)
    # Wait until stream deleted, default is 10 * 18 seconds.
    client.get_waiter('stream_not_exists').wait(StreamName=stream_name)
  request.addfinalizer(fin)

  args = stream_name
  def func(q):
    dataset = tfio.experimental.IODataset.from_kinesis(q)
    dataset = dataset.map(lambda e: (e.data, e.partition))
    dataset = dataset.take(10)
    return dataset
  expected = list(zip([v.encode() for v in val], [k.encode() for k in key]))

  return args, func, expected

# Source of audio are based on the following:
#   https://commons.wikimedia.org/wiki/File:ZASFX_ADSR_no_sustain.ogg
# OGG: ZASFX_ADSR_no_sustain.ogg.
# WAV: oggdec ZASFX_ADSR_no_sustain.ogg # => ZASFX_ADSR_no_sustain.wav
# WAV (24 bit):
#   sox ZASFX_ADSR_no_sustain.wav -b 24 ZASFX_ADSR_no_sustain.24.wav
#   sox ZASFX_ADSR_no_sustain.24.wav ZASFX_ADSR_no_sustain.24.s32
# FLAC: ffmpeg -i ZASFX_ADSR_no_sustain.wav ZASFX_ADSR_no_sustain.flac
@pytest.fixture(name="audio_wav", scope="module")
def fixture_audio_wav():
  """fixture_audio_wav"""
  path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_audio", "ZASFX_ADSR_no_sustain.wav")
  audio = tf.audio.decode_wav(tf.io.read_file(path))
  value = audio.audio * (1 << 15)
  value = tf.cast(value, tf.int16)

  args = path
  func = lambda args: tfio.IODataset.graph(tf.int16).from_audio(args)
  expected = [v for _, v in enumerate(value)]

  return args, func, expected

@pytest.fixture(name="audio_wav_24", scope="module")
def fixture_audio_wav_24():
  """fixture_audio_wav_24"""
  path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_audio", "ZASFX_ADSR_no_sustain.24.wav")
  raw_path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_audio", "ZASFX_ADSR_no_sustain.24.s32")
  value = np.fromfile(raw_path, np.int32)
  value = np.reshape(value, [14336, 2])
  value = tf.constant(value)

  args = path
  func = lambda args: tfio.IODataset.graph(tf.int32).from_audio(args)
  expected = [v for _, v in enumerate(value)]

  return args, func, expected

@pytest.fixture(name="audio_ogg", scope="module")
def fixture_audio_ogg():
  """fixture_audio_ogg"""
  ogg_path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_audio", "ZASFX_ADSR_no_sustain.ogg")
  path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_audio", "ZASFX_ADSR_no_sustain.wav")
  audio = tf.audio.decode_wav(tf.io.read_file(path))
  value = audio.audio * (1 << 15)
  value = tf.cast(value, tf.int16)

  args = ogg_path
  func = lambda args: tfio.IODataset.graph(tf.int16).from_audio(args)
  expected = [v for _, v in enumerate(value)]

  return args, func, expected

@pytest.fixture(name="audio_flac", scope="module")
def fixture_audio_flac():
  """fixture_audio_flac"""
  path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_audio", "ZASFX_ADSR_no_sustain.flac")
  wav_path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_audio", "ZASFX_ADSR_no_sustain.wav")
  audio = tf.audio.decode_wav(tf.io.read_file(wav_path))
  value = audio.audio * (1 << 15)
  value = tf.cast(value, tf.int16)

  args = path
  func = lambda args: tfio.IODataset.graph(tf.int16).from_audio(args)
  expected = [v for _, v in enumerate(value)]

  return args, func, expected

@pytest.fixture(name="hdf5", scope="module")
def fixture_hdf5(request):
  """fixture_hdf5"""
  import h5py # pylint: disable=import-outside-toplevel

  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "test.h5")

  data = list(range(5000))

  string_data = ["D" + str(i) for i in range(5000)]

  complex_data = [(1. + 2.j) * i for i in range(5000)]

  with h5py.File(filename, 'w') as f:
    f.create_dataset('uint8', data=np.asarray(data, np.uint8) % 256, dtype='u1')
    f.create_dataset('uint16', data=np.asarray(data, np.uint16), dtype='u2')
    f.create_dataset('uint32', data=np.asarray(data, np.uint32), dtype='u4')
    f.create_dataset('uint64', data=np.asarray(data, np.uint64), dtype='u8')
    f.create_dataset('int8', data=np.asarray(data, np.int8) % 128, dtype='i1')
    f.create_dataset('int16', data=np.asarray(data, np.int16), dtype='i2')
    f.create_dataset('int32', data=np.asarray(data, np.int32), dtype='i4')
    f.create_dataset('int64', data=np.asarray(data, np.int64), dtype='i8')
    f.create_dataset('float32', data=np.asarray(data, np.float32), dtype='f4')
    f.create_dataset('float64', data=np.asarray(data, np.float64), dtype='f8')
    f.create_dataset('complex64', data=np.asarray(complex_data, np.complex64))
    f.create_dataset('complex128', data=np.asarray(complex_data, np.complex128))
    f.create_dataset('string', data=np.asarray(string_data, '<S5'))
  args = filename
  def func(args):
    """func"""
    u8 = tfio.IODataset.from_hdf5(args, dataset='/uint8')
    u16 = tfio.IODataset.from_hdf5(args, dataset='/uint16')
    u32 = tfio.IODataset.from_hdf5(args, dataset='/uint32')
    u64 = tfio.IODataset.from_hdf5(args, dataset='/uint64')
    i8 = tfio.IODataset.from_hdf5(args, dataset='/int8')
    i16 = tfio.IODataset.from_hdf5(args, dataset='/int16')
    i32 = tfio.IODataset.from_hdf5(args, dataset='/int32')
    i64 = tfio.IODataset.from_hdf5(args, dataset='/int64')
    f32 = tfio.IODataset.from_hdf5(args, dataset='/float32')
    f64 = tfio.IODataset.from_hdf5(args, dataset='/float64')
    c64 = tfio.IODataset.from_hdf5(args, dataset='/complex64')
    c128 = tfio.IODataset.from_hdf5(args, dataset='/complex128')
    ss = tfio.IODataset.from_hdf5(args, dataset='/string')
    return tf.data.Dataset.zip(
        (u8, u16, u32, u64, i8, i16, i32, i64, f32, f64, c64, c128, ss))
  expected = list(zip(
      (np.asarray(data, np.uint8) % 256).tolist(),
      np.asarray(data, np.uint16).tolist(),
      np.asarray(data, np.uint32).tolist(),
      np.asarray(data, np.uint64).tolist(),
      (np.asarray(data, np.int8) % 128) .tolist(),
      np.asarray(data, np.int16).tolist(),
      np.asarray(data, np.int32).tolist(),
      np.asarray(data, np.int64).tolist(),
      np.asarray(data, np.float32).tolist(),
      np.asarray(data, np.float64).tolist(),
      np.asarray(complex_data, np.complex64).tolist(),
      np.asarray(complex_data, np.complex128).tolist(),
      np.asarray(string_data, '<S5').tolist()))
  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  return args, func, expected

@pytest.fixture(name="hdf5_graph", scope="module")
def fixture_hdf5_graph(request):
  """fixture_hdf5_graph"""
  import h5py # pylint: disable=import-outside-toplevel

  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "test.h5")

  data = list(range(5000))

  string_data = ["D" + str(i) for i in range(5000)]

  complex_data = [(1. + 2.j) * i for i in range(5000)]

  with h5py.File(filename, 'w') as f:
    f.create_dataset('uint8', data=np.asarray(data, np.uint8) % 256, dtype='u1')
    f.create_dataset('uint16', data=np.asarray(data, np.uint16), dtype='u2')
    f.create_dataset('uint32', data=np.asarray(data, np.uint32), dtype='u4')
    f.create_dataset('uint64', data=np.asarray(data, np.uint64), dtype='u8')
    f.create_dataset('int8', data=np.asarray(data, np.int8) % 128, dtype='i1')
    f.create_dataset('int16', data=np.asarray(data, np.int16), dtype='i2')
    f.create_dataset('int32', data=np.asarray(data, np.int32), dtype='i4')
    f.create_dataset('int64', data=np.asarray(data, np.int64), dtype='i8')
    f.create_dataset('float32', data=np.asarray(data, np.float32), dtype='f4')
    f.create_dataset('float64', data=np.asarray(data, np.float64), dtype='f8')
    f.create_dataset('complex64', data=np.asarray(complex_data, np.complex64))
    f.create_dataset('complex128', data=np.asarray(complex_data, np.complex128))
    f.create_dataset('string', data=np.asarray(string_data, '<S5'))
  args = filename
  def func(args):
    """func"""
    u8 = tfio.IODataset.from_hdf5(args, dataset='/uint8', spec=tf.uint8)
    u16 = tfio.IODataset.from_hdf5(args, dataset='/uint16', spec=tf.uint16)
    u32 = tfio.IODataset.from_hdf5(args, dataset='/uint32', spec=tf.uint32)
    u64 = tfio.IODataset.from_hdf5(args, dataset='/uint64', spec=tf.uint64)
    i8 = tfio.IODataset.from_hdf5(args, dataset='/int8', spec=tf.int8)
    i16 = tfio.IODataset.from_hdf5(args, dataset='/int16', spec=tf.int16)
    i32 = tfio.IODataset.from_hdf5(args, dataset='/int32', spec=tf.int32)
    i64 = tfio.IODataset.from_hdf5(args, dataset='/int64', spec=tf.int64)
    f32 = tfio.IODataset.from_hdf5(args, dataset='/float32', spec=tf.float32)
    f64 = tfio.IODataset.from_hdf5(args, dataset='/float64', spec=tf.float64)
    c64 = tfio.IODataset.from_hdf5(
        args, dataset='/complex64', spec=tf.complex64)
    c128 = tfio.IODataset.from_hdf5(
        args, dataset='/complex128', spec=tf.complex128)
    ss = tfio.IODataset.from_hdf5(args, dataset='/string', spec=tf.string)
    return tf.data.Dataset.zip(
        (u8, u16, u32, u64, i8, i16, i32, i64, f32, f64, c64, c128, ss))
  expected = list(zip(
      (np.asarray(data, np.uint8) % 256).tolist(),
      np.asarray(data, np.uint16).tolist(),
      np.asarray(data, np.uint32).tolist(),
      np.asarray(data, np.uint64).tolist(),
      (np.asarray(data, np.int8) % 128) .tolist(),
      np.asarray(data, np.int16).tolist(),
      np.asarray(data, np.int32).tolist(),
      np.asarray(data, np.int64).tolist(),
      np.asarray(data, np.float32).tolist(),
      np.asarray(data, np.float64).tolist(),
      np.asarray(complex_data, np.complex64).tolist(),
      np.asarray(complex_data, np.complex128).tolist(),
      np.asarray(string_data, '<S5').tolist()))
  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  return args, func, expected

@pytest.fixture(name="to_file")
def fixture_to_file(request):
  """fixture_to_file"""
  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "data.text")

  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  args = filename
  func = tfio.experimental.IODataset.to_file
  def data_func(filename):
    with open(filename, "r") as f:
      lines = list(f)
    return lines

  return args, func, data_func

@pytest.fixture(name="numpy")
def fixture_numpy():
  """fixture_numpy"""

  data = [[i, i+1, i+2] for i in range(0, 5000)]

  args = np.asarray(data)
  func = tfio.experimental.IODataset.from_numpy
  expected = data

  return args, func, expected

@pytest.fixture(name="numpy_structure")
def fixture_numpy_structure():
  """fixture_numpy_structure"""

  d1 = [[i, i+1, i+2] for i in range(0, 5000)]
  d2 = [[i+2, i+1, i] for i in range(0, 5000)]

  args = (np.asarray(d1), np.asarray(d2))
  func = tfio.experimental.IODataset.from_numpy
  expected = list(zip(d1, d2))

  return args, func, expected

@pytest.fixture(name="numpy_file_tuple")
def fixture_numpy_file_tuple(request):
  """fixture_numpy_file_tuple"""

  d1 = [[i, i+1, i+2] for i in range(0, 5000)]
  d2 = [[i+2, i+1, i] for i in range(0, 5000)]

  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "numpy_file.npz")

  np.savez(filename, np.asarray(d1), np.asarray(d2))

  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  args = filename
  func = tfio.experimental.IODataset.from_numpy_file
  expected = list(zip(d1, d2))

  return args, func, expected

@pytest.fixture(name="numpy_file_dict")
def fixture_numpy_file_dict(request):
  """fixture_numpy_file_dict"""

  d1 = [[i, i+1, i+2] for i in range(0, 5000)]
  d2 = [[i+2, i+1, i] for i in range(0, 5000)]

  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "numpy_file.npz")

  np.savez(filename, d2=np.asarray(d2), d1=np.asarray(d1))

  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  args = filename
  def func(f):
    dataset = tfio.experimental.IODataset.from_numpy_file(f)
    dataset = dataset.map(lambda e: (e['d1'], e['d2']))
    return dataset
  expected = list(zip(d1, d2))

  return args, func, expected

@pytest.fixture(name="numpy_file_tuple_graph")
def fixture_numpy_file_tuple_graph(request):
  """fixture_numpy_file_tuple_graph"""

  d1 = [[i, i+1, i+2] for i in range(0, 5000)]
  d2 = [[i+2, i+1, i] for i in range(0, 5000)]

  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "numpy_file.npz")

  np.savez(filename, np.asarray(d1), np.asarray(d2))

  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  args = filename
  def func(f):
    return tfio.experimental.IODataset.from_numpy_file(
        f, spec=(tf.int64, tf.int64))
  expected = list(zip(d1, d2))

  return args, func, expected

@pytest.fixture(name="numpy_file_dict_graph")
def fixture_numpy_file_dict_graph(request):
  """fixture_numpy_file_dict_graph"""

  d1 = [[i, i+1, i+2] for i in range(0, 5000)]
  d2 = [[i+2, i+1, i] for i in range(0, 5000)]

  tmp_path = tempfile.mkdtemp()
  filename = os.path.join(tmp_path, "numpy_file.npz")

  np.savez(filename, d2=np.asarray(d2), d1=np.asarray(d1))

  def fin():
    shutil.rmtree(tmp_path)
  request.addfinalizer(fin)

  args = filename
  def func(f):
    dataset = tfio.experimental.IODataset.from_numpy_file(
        f, spec={'d1': tf.int64, 'd2': tf.int64})
    dataset = dataset.map(lambda e: (e['d1'], e['d2']))
    return dataset
  expected = list(zip(d1, d2))

  return args, func, expected

# This test make sure dataset works in tf.keras inference.
# The requirement for tf.keras inference is the support of `iter()`:
#   entries = [e for e in dataset]
@pytest.mark.parametrize(
    ("io_dataset_fixture"),
    [
        pytest.param("mnist"),
        pytest.param("mnist_gz"),
        pytest.param("lmdb"),
        pytest.param(
            "prometheus",
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param("audio_wav"),
        pytest.param("audio_wav_24"),
        pytest.param("audio_ogg"),
        pytest.param("audio_flac"),
        pytest.param(
            "prometheus_scrape",
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param(
            "kinesis",
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support kinesis"),
            ],
        ),
        pytest.param("pubsub"),
        pytest.param("hdf5"),
        pytest.param("grpc"),
        pytest.param("numpy"),
        pytest.param("numpy_structure"),
        pytest.param("numpy_file_tuple"),
        pytest.param("numpy_file_dict"),
    ],
    ids=[
        "mnist",
        "mnist[gz]",
        "lmdb",
        "prometheus",
        "audio[wav]",
        "audio[wav/24bit]",
        "audio[ogg]",
        "audio[flac]",
        "prometheus[scrape]",
        "kinesis",
        "pubsub",
        "hdf5",
        "grpc",
        "numpy",
        "numpy[structure]",
        "numpy[file/tuple]",
        "numpy[file/dict]",
    ],
)
def test_io_dataset_basic(fixture_lookup, io_dataset_fixture):
  """test_io_dataset_basic"""
  args, func, expected = fixture_lookup(io_dataset_fixture)

  dataset = func(args)
  entries = list(dataset)

  assert len(entries) == len(expected)
  assert all([element_equal(a, b) for (a, b) in zip(entries, expected)])

# This test makes sure basic dataset operations (take, batch) work.
@pytest.mark.parametrize(
    ("io_dataset_fixture"),
    [
        pytest.param("mnist"),
        pytest.param("mnist_gz"),
        pytest.param(
            "lmdb",
            marks=[
                pytest.mark.xfail(reason="TODO"),
            ],
        ),
        pytest.param(
            "prometheus",
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param("audio_wav"),
        pytest.param("audio_wav_24"),
        pytest.param("audio_ogg"),
        pytest.param("audio_flac"),
        pytest.param(
            "prometheus_scrape",
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param("hdf5"),
        pytest.param("grpc"),
        pytest.param("numpy"),
        pytest.param("numpy_structure"),
        pytest.param("numpy_file_tuple"),
        pytest.param("numpy_file_dict"),
    ],
    ids=[
        "mnist",
        "mnist[gz]",
        "lmdb",
        "prometheus",
        "audio[wav]",
        "audio[wav/24bit]",
        "audio[ogg]",
        "audio[flac]",
        "prometheus[scrape]",
        "hdf5",
        "grpc",
        "numpy",
        "numpy[structure]",
        "numpy[file/tuple]",
        "numpy[file/dict]",
    ],
)
def test_io_dataset_basic_operation(fixture_lookup, io_dataset_fixture):
  """test_io_dataset_basic_operation"""
  args, func, expected = fixture_lookup(io_dataset_fixture)

  dataset = func(args)

  # Test of take
  expected_taken = expected[:5]
  entries_taken = list(dataset.take(5))

  assert len(entries_taken) == len(expected_taken)
  assert all([
      element_equal(a, b) for (a, b) in zip(entries_taken, expected_taken)])

  # Test of batch
  indices = list(range(0, len(expected), 3))
  indices = list(zip(indices, indices[1:] + [len(expected)]))

  expected_batched = [element_slice(expected, i, j) for i, j in indices]
  entries_batched = list(dataset.batch(3))

  assert len(entries_batched) == len(expected_batched)
  assert all([
      all([element_equal(i, j) for (i, j) in zip(a, b)]) for (a, b) in zip(
          entries_batched, expected_batched)])

# This test makes sure dataset works in tf.keras training.
# The requirement for tf.keras training is the support of multiple `iter()`
# runs with consistent result:
#   entries_1 = [e for e in dataset]
#   entries_2 = [e for e in dataset]
#   assert entries_1 = entries_2
@pytest.mark.parametrize(
    ("io_dataset_fixture"),
    [
        pytest.param("mnist"),
        pytest.param("mnist_gz"),
        pytest.param(
            "lmdb",
            marks=[
                pytest.mark.xfail(reason="TODO"),
            ],
        ),
        pytest.param(
            "prometheus",
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param("audio_wav"),
        pytest.param("audio_wav_24"),
        pytest.param("audio_ogg"),
        pytest.param("audio_flac"),
        pytest.param("hdf5"),
        pytest.param("grpc"),
        pytest.param("numpy"),
        pytest.param("numpy_structure"),
        pytest.param("numpy_file_tuple"),
        pytest.param("numpy_file_dict"),
    ],
    ids=[
        "mnist",
        "mnist[gz]",
        "lmdb",
        "prometheus",
        "audio[wav]",
        "audio[wav/24bit]",
        "audio[ogg]",
        "audio[flac]",
        "hdf5",
        "grpc",
        "numpy",
        "numpy[structure]",
        "numpy[file/tuple]",
        "numpy[file/dict]",
    ],
)
def test_io_dataset_for_training(fixture_lookup, io_dataset_fixture):
  """test_io_dataset_for_training"""
  args, func, expected = fixture_lookup(io_dataset_fixture)

  dataset = func(args)

  # Run of dataset iteration
  entries = list(dataset)

  assert len(entries) == len(expected)
  assert all([element_equal(a, b) for (a, b) in zip(entries, expected)])

  # A re-run of dataset iteration yield the same results, needed for training.
  entries = list(dataset)

  assert len(entries) == len(expected)
  assert all([element_equal(a, b) for (a, b) in zip(entries, expected)])

# This test makes sure dataset in dataet and parallelism work.
# It is not needed for tf.keras but could be useful
# for complex data processing.
@pytest.mark.parametrize(
    ("io_dataset_fixture", "num_parallel_calls"),
    [
        pytest.param("mnist", None),
        pytest.param("mnist", 2),
        pytest.param("mnist_gz", None),
        pytest.param("mnist_gz", 2),
        pytest.param(
            "lmdb", None,
            marks=[
                pytest.mark.skip(reason="TODO"),
            ],
        ),
        pytest.param(
            "lmdb", 2,
            marks=[
                pytest.mark.skip(reason="TODO"),
            ],
        ),
        pytest.param(
            "prometheus_graph", None,
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param(
            "prometheus_graph", 2,
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param("audio_wav", None),
        pytest.param("audio_wav", 2),
        pytest.param("audio_wav_24", None),
        pytest.param("audio_wav_24", 2),
        pytest.param("audio_ogg", None),
        pytest.param("audio_ogg", 2),
        pytest.param("audio_flac", None),
        pytest.param("audio_flac", 2),
        pytest.param("hdf5_graph", None),
        pytest.param(
            "hdf5_graph", 2,
            marks=[
                pytest.mark.skip(reason="TODO"),
            ],
        ),
        pytest.param("numpy_file_tuple_graph", None),
        pytest.param("numpy_file_tuple_graph", 2),
        pytest.param("numpy_file_dict_graph", None),
        pytest.param("numpy_file_dict_graph", 2),
    ],
    ids=[
        "mnist",
        "mnist|2",
        "mnist[gz]",
        "mnist[gz]|2",
        "lmdb",
        "lmdb|2",
        "prometheus",
        "prometheus|2",
        "audio[wav]",
        "audio[wav]|2",
        "audio[wav/24bit]",
        "audio[wav/24bit]|2",
        "audio[ogg]",
        "audio[ogg]|2",
        "audio[flac]",
        "audio[flac]|2",
        "hdf5",
        "hdf5|2",
        "numpy[file/tuple]",
        "numpy[file/tuple]|2",
        "numpy[file/dict]",
        "numpy[file/dict]|2",
    ],
)
def test_io_dataset_in_dataset_parallel(
    fixture_lookup, io_dataset_fixture, num_parallel_calls):
  """test_io_dataset_in_dataset_parallel"""
  args, func, expected = fixture_lookup(io_dataset_fixture)

  dataset = func(args)

  # Note: @tf.function is actually not needed, as tf.data.Dataset
  # will automatically wrap the `func` into a graph anyway.
  # The following is purely for explanation purposes.
  @tf.function
  def f(v):
    return func(v)

  args_dataset = tf.data.Dataset.from_tensor_slices([args, args])

  dataset = args_dataset.map(f, num_parallel_calls=num_parallel_calls)

  item = 0
  # Notice dataset in dataset:
  for d in dataset:
    i = 0
    for v in d:
      assert element_equal(expected[i], v)
      i += 1
    assert i == len(expected)
    item += 1
  assert item == 2

# This test is a benchmark for dataset, could invoke/skip/disalbe through:
#   --benchmark-only
#   --benchmark-skip
#   --benchmark-disable
@pytest.mark.benchmark(
    group="io_dataset",
)
@pytest.mark.parametrize(
    ("io_dataset_fixture"),
    [
        pytest.param("mnist"),
        pytest.param("lmdb"),
        pytest.param(
            "prometheus",
            marks=[
                pytest.mark.skipif(
                    sys.platform == "darwin",
                    reason="TODO macOS does not support prometheus"),
            ],
        ),
        pytest.param("audio_wav"),
        pytest.param("audio_wav_24"),
        pytest.param("audio_ogg"),
        pytest.param("audio_flac"),
        pytest.param("hdf5"),
        pytest.param("numpy"),
        pytest.param("numpy_structure"),
        pytest.param("numpy_file_tuple"),
        pytest.param("numpy_file_dict"),
    ],
    ids=[
        "mnist",
        "lmdb",
        "prometheus",
        "audio[wav]",
        "audio[wav/24bit]",
        "audio[ogg]",
        "audio[flac]",
        "hdf5",
        "numpy",
        "numpy[structure]",
        "numpy[file/tuple]",
        "numpy[file/dict]",
    ],
)
def test_io_dataset_benchmark(benchmark, fixture_lookup, io_dataset_fixture):
  """test_io_dataset_benchmark"""
  args, func, expected = fixture_lookup(io_dataset_fixture)

  def f(v):
    dataset = func(v)
    entries = list(dataset)
    return entries

  entries = benchmark(f, args)

  assert len(entries) == len(expected)
  assert all([element_equal(a, b) for (a, b) in zip(entries, expected)])

@pytest.mark.parametrize(
    ("io_dataset_fixture"),
    [
        pytest.param("to_file"),
    ],
    ids=[
        "to_file",
    ],
)
def test_io_dataset_to(fixture_lookup, io_dataset_fixture):
  """test_io_dataset_to"""
  args, func, data_func = fixture_lookup(io_dataset_fixture)

  dataset = tf.data.Dataset.range(1000)
  dataset = dataset.batch(15)
  dataset = dataset.map(tf.strings.as_string)
  dataset = dataset.map(lambda e: e + "\n")

  entries = func(dataset, args)
  assert (entries) == 1000

  lines = data_func(args)
  return np.all(lines == ["{}\n".format(i) for i in range(1000)])

@pytest.mark.parametrize(
    ("io_dataset_fixture"),
    [
        pytest.param("to_file"),
    ],
    ids=[
        "to_file",
    ],
)
def test_io_dataset_to_in_dataset(fixture_lookup, io_dataset_fixture):
  """test_io_dataset_to_in_dataset"""
  args, func, data_func = fixture_lookup(io_dataset_fixture)

  def f(v):
    dataset = tf.data.Dataset.range(1000)
    dataset = dataset.batch(15)
    dataset = dataset.map(tf.strings.as_string)
    dataset = dataset.map(lambda e: e + "\n")

    return func(dataset, v)

  dataset = tf.data.Dataset.from_tensor_slices([args])
  dataset = dataset.map(f)

  entries = list(dataset)

  assert entries == [1000]

  lines = data_func(args)
  return np.all(lines == ["{}\n".format(i) for i in range(1000)])