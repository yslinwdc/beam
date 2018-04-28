#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Unit tests for the setup module."""

import logging
import os
import shutil
import tempfile
import unittest

import mock

from apache_beam.io.filesystems import FileSystems
from apache_beam.options.pipeline_options import GoogleCloudOptions
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.options.pipeline_options import SetupOptions
from apache_beam.runners.dataflow.internal import dependency
from apache_beam.runners.dataflow.internal import names

# Protect against environments where GCS library is not available.
# pylint: disable=wrong-import-order, wrong-import-position
try:
  from apitools.base.py.exceptions import HttpError
except ImportError:
  HttpError = None
# pylint: enable=wrong-import-order, wrong-import-position

#TODO(angoenka): Clean test cases and mock Stager.
@unittest.skipIf(HttpError is None, 'GCP dependencies are not installed')
class SetupTest(unittest.TestCase):

  def setUp(self):
    self._temp_dir = None

  def make_temp_dir(self):
    if self._temp_dir is None:
      self._temp_dir = tempfile.mkdtemp()
    return tempfile.mkdtemp(dir=self._temp_dir)

  def tearDown(self):
    if self._temp_dir:
      shutil.rmtree(self._temp_dir)

  def update_options(self, options):
    setup_options = options.view_as(SetupOptions)
    setup_options.sdk_location = ''
    google_cloud_options = options.view_as(GoogleCloudOptions)
    if google_cloud_options.temp_location is None:
      google_cloud_options.temp_location = google_cloud_options.staging_location

  def create_temp_file(self, path, contents):
    with open(path, 'w') as f:
      f.write(contents)
      return f.name

  def populate_requirements_cache(self, requirements_file, cache_dir):
    _ = requirements_file
    self.create_temp_file(os.path.join(cache_dir, 'abc.txt'), 'nothing')
    self.create_temp_file(os.path.join(cache_dir, 'def.txt'), 'nothing')

  def test_no_staging_location(self):
    with self.assertRaises(RuntimeError) as cm:
      dependency.stage_job_resources(PipelineOptions())
    self.assertEqual('The --staging_location option must be specified.',
                     cm.exception.args[0])

  def test_no_temp_location(self):
    staging_dir = self.make_temp_dir()
    options = PipelineOptions()
    google_cloud_options = options.view_as(GoogleCloudOptions)
    google_cloud_options.staging_location = staging_dir
    self.update_options(options)
    google_cloud_options.temp_location = None
    with self.assertRaises(RuntimeError) as cm:
      dependency.stage_job_resources(options)
    self.assertEqual('The --temp_location option must be specified.',
                     cm.exception.args[0])

  def test_no_main_session(self):
    staging_dir = self.make_temp_dir()
    options = PipelineOptions()

    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    options.view_as(SetupOptions).save_main_session = False
    self.update_options(options)

    self.assertEqual([], dependency.stage_job_resources(options))

  def test_with_main_session(self):
    staging_dir = self.make_temp_dir()
    options = PipelineOptions()

    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    options.view_as(SetupOptions).save_main_session = True
    self.update_options(options)

    self.assertEqual([names.PICKLED_MAIN_SESSION_FILE],
                     dependency.stage_job_resources(options))
    self.assertTrue(
        os.path.isfile(
            os.path.join(staging_dir, names.PICKLED_MAIN_SESSION_FILE)))

  def test_default_resources(self):
    staging_dir = self.make_temp_dir()
    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)

    self.assertEqual([], dependency.stage_job_resources(options))

  def test_with_requirements_file(self):
    staging_dir = self.make_temp_dir()
    requirements_cache_dir = self.make_temp_dir()
    source_dir = self.make_temp_dir()

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).requirements_cache = requirements_cache_dir
    options.view_as(SetupOptions).requirements_file = os.path.join(
        source_dir, dependency.REQUIREMENTS_FILE)
    self.create_temp_file(
        os.path.join(source_dir, dependency.REQUIREMENTS_FILE), 'nothing')
    self.assertEqual(
        sorted([dependency.REQUIREMENTS_FILE, 'abc.txt', 'def.txt']),
        sorted(
            dependency.stage_job_resources(
                options,
                populate_requirements_cache=self.populate_requirements_cache)))
    self.assertTrue(
        os.path.isfile(os.path.join(staging_dir, dependency.REQUIREMENTS_FILE)))
    self.assertTrue(os.path.isfile(os.path.join(staging_dir, 'abc.txt')))
    self.assertTrue(os.path.isfile(os.path.join(staging_dir, 'def.txt')))

  def test_requirements_file_not_present(self):
    staging_dir = self.make_temp_dir()
    with self.assertRaises(RuntimeError) as cm:
      options = PipelineOptions()
      options.view_as(GoogleCloudOptions).staging_location = staging_dir
      self.update_options(options)
      options.view_as(SetupOptions).requirements_file = 'nosuchfile'
      dependency.stage_job_resources(
          options, populate_requirements_cache=self.populate_requirements_cache)
    self.assertEqual(
        cm.exception.args[0],
        'The file %s cannot be found. It was specified in the '
        '--requirements_file command line option.' % 'nosuchfile')

  def test_with_requirements_file_and_cache(self):
    staging_dir = self.make_temp_dir()
    source_dir = self.make_temp_dir()

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).requirements_file = os.path.join(
        source_dir, dependency.REQUIREMENTS_FILE)
    options.view_as(SetupOptions).requirements_cache = self.make_temp_dir()
    self.create_temp_file(
        os.path.join(source_dir, dependency.REQUIREMENTS_FILE), 'nothing')
    self.assertEqual(
        sorted([dependency.REQUIREMENTS_FILE, 'abc.txt', 'def.txt']),
        sorted(
            dependency.stage_job_resources(
                options,
                populate_requirements_cache=self.populate_requirements_cache)))
    self.assertTrue(
        os.path.isfile(os.path.join(staging_dir, dependency.REQUIREMENTS_FILE)))
    self.assertTrue(os.path.isfile(os.path.join(staging_dir, 'abc.txt')))
    self.assertTrue(os.path.isfile(os.path.join(staging_dir, 'def.txt')))

  def test_with_setup_file(self):
    staging_dir = self.make_temp_dir()
    source_dir = self.make_temp_dir()
    self.create_temp_file(os.path.join(source_dir, 'setup.py'), 'notused')

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).setup_file = os.path.join(
        source_dir, 'setup.py')

    self.assertEqual(
        [dependency.WORKFLOW_TARBALL_FILE],
        dependency.stage_job_resources(
            options,
            # We replace the build setup command because a realistic one would
            # require the setuptools package to be installed. Note that we can't
            # use "touch" here to create the expected output tarball file, since
            # touch is not available on Windows, so we invoke python to produce
            # equivalent behavior.
            build_setup_args=[
                'python', '-c', 'open(__import__("sys").argv[1], "a")',
                os.path.join(source_dir, dependency.WORKFLOW_TARBALL_FILE)
            ],
            temp_dir=source_dir))
    self.assertTrue(
        os.path.isfile(
            os.path.join(staging_dir, dependency.WORKFLOW_TARBALL_FILE)))

  def test_setup_file_not_present(self):
    staging_dir = self.make_temp_dir()

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).setup_file = 'nosuchfile'

    with self.assertRaises(RuntimeError) as cm:
      dependency.stage_job_resources(options)
    self.assertEqual(
        cm.exception.args[0],
        'The file %s cannot be found. It was specified in the '
        '--setup_file command line option.' % 'nosuchfile')

  def test_setup_file_not_named_setup_dot_py(self):
    staging_dir = self.make_temp_dir()
    source_dir = self.make_temp_dir()

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).setup_file = (
        os.path.join(source_dir, 'xyz-setup.py'))

    self.create_temp_file(os.path.join(source_dir, 'xyz-setup.py'), 'notused')
    with self.assertRaises(RuntimeError) as cm:
      dependency.stage_job_resources(options)
    self.assertTrue(cm.exception.args[0].startswith(
        'The --setup_file option expects the full path to a file named '
        'setup.py instead of '))

  def build_fake_pip_download_command_handler(self, has_wheels):
    """A stub for apache_beam.utils.processes.check_call that imitates pip.

    Args:
      has_wheels: Whether pip fake should have a whl distribution of packages.
    """

    def pip_fake(args):
      """Fakes fetching a package from pip by creating a temporary file.

      Args:
        args: a complete list of command line arguments to invoke pip.
          The fake is sensitive to the order of the arguments.
          Supported commands:

          1) Download SDK sources file:
          python pip -m download --dest /tmp/dir apache-beam==2.0.0 \
              --no-deps --no-binary :all:

          2) Download SDK binary wheel file:
          python pip -m download --dest /tmp/dir apache-beam==2.0.0 \
              --no-deps --no-binary :all: --python-version 27 \
              --implementation cp --abi cp27mu --platform manylinux1_x86_64
      """
      package_file = None
      if len(args) >= 8:
        # package_name==x.y.z
        if '==' in args[6]:
          distribution_name = args[6][0:args[6].find('==')]
          distribution_version = args[6][args[6].find('==') + 2:]

          if args[8] == '--no-binary':
            package_file = '%s-%s.zip' % (distribution_name,
                                          distribution_version)
          elif args[8] == '--only-binary' and len(args) >= 18:
            if not has_wheels:
              # Imitate the case when desired wheel distribution is not in PyPI.
              raise RuntimeError('No matching distribution.')

            # Per PEP-0427 in wheel filenames non-alphanumeric characters
            # in distribution name are replaced with underscore.
            distribution_name = distribution_name.replace('-', '_')
            package_file = '%s-%s-%s%s-%s-%s.whl' % (
                distribution_name,
                distribution_version,
                args[13],  # implementation
                args[11],  # python version
                args[15],  # abi tag
                args[17]  # platform
            )

      assert package_file, 'Pip fake does not support the command: ' + str(args)
      self.create_temp_file(
          FileSystems.join(args[5], package_file), 'Package content.')

    return pip_fake

  def test_sdk_location_default(self):
    staging_dir = self.make_temp_dir()
    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = 'default'

    with mock.patch(
        'apache_beam.utils.processes.check_call',
        self.build_fake_pip_download_command_handler(has_wheels=False)):
      staged_resources = dependency.stage_job_resources(
          options, temp_dir=self.make_temp_dir())

    self.assertEqual([names.DATAFLOW_SDK_TARBALL_FILE], staged_resources)

    with open(os.path.join(staging_dir, names.DATAFLOW_SDK_TARBALL_FILE)) as f:
      self.assertEqual(f.read(), 'Package content.')

  def test_sdk_location_default_with_wheels(self):
    staging_dir = self.make_temp_dir()

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = 'default'

    with mock.patch(
        'apache_beam.utils.processes.check_call',
        self.build_fake_pip_download_command_handler(has_wheels=True)):
      staged_resources = dependency.stage_job_resources(
          options, temp_dir=self.make_temp_dir())

      self.assertEqual(len(staged_resources), 2)
      self.assertEqual(staged_resources[0], names.DATAFLOW_SDK_TARBALL_FILE)
      # Exact name depends on the version of the SDK.
      self.assertTrue(staged_resources[1].endswith('whl'))
      for name in staged_resources:
        with open(os.path.join(staging_dir, name)) as f:
          self.assertEqual(f.read(), 'Package content.')

  def test_sdk_location_local_directory(self):
    staging_dir = self.make_temp_dir()
    sdk_location = self.make_temp_dir()
    self.create_temp_file(
        os.path.join(sdk_location, names.DATAFLOW_SDK_TARBALL_FILE),
        'Package content.')

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = sdk_location

    self.assertEqual([names.DATAFLOW_SDK_TARBALL_FILE],
                     dependency.stage_job_resources(options))
    tarball_path = os.path.join(staging_dir, names.DATAFLOW_SDK_TARBALL_FILE)
    with open(tarball_path) as f:
      self.assertEqual(f.read(), 'Package content.')

  def test_sdk_location_local_source_file(self):
    staging_dir = self.make_temp_dir()
    sdk_directory = self.make_temp_dir()
    sdk_filename = 'apache-beam-3.0.0.tar.gz'
    sdk_location = os.path.join(sdk_directory, sdk_filename)
    self.create_temp_file(sdk_location, 'Package content.')

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = sdk_location

    self.assertEqual([names.DATAFLOW_SDK_TARBALL_FILE],
                     dependency.stage_job_resources(options))
    tarball_path = os.path.join(staging_dir, names.DATAFLOW_SDK_TARBALL_FILE)
    with open(tarball_path) as f:
      self.assertEqual(f.read(), 'Package content.')

  def test_sdk_location_local_wheel_file(self):
    staging_dir = self.make_temp_dir()
    sdk_directory = self.make_temp_dir()
    sdk_filename = 'apache_beam-1.0.0-cp27-cp27mu-manylinux1_x86_64.whl'
    sdk_location = os.path.join(sdk_directory, sdk_filename)
    self.create_temp_file(sdk_location, 'Package content.')

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = sdk_location

    self.assertEqual([sdk_filename], dependency.stage_job_resources(options))
    tarball_path = os.path.join(staging_dir, sdk_filename)
    with open(tarball_path) as f:
      self.assertEqual(f.read(), 'Package content.')

  def test_sdk_location_local_directory_not_present(self):
    staging_dir = self.make_temp_dir()
    sdk_location = 'nosuchdir'
    with self.assertRaises(RuntimeError) as cm:
      options = PipelineOptions()
      options.view_as(GoogleCloudOptions).staging_location = staging_dir
      self.update_options(options)
      options.view_as(SetupOptions).sdk_location = sdk_location

      dependency.stage_job_resources(options)
    self.assertEqual(
        'The file "%s" cannot be found. Its '
        'location was specified by the --sdk_location command-line option.' %
        sdk_location, cm.exception.args[0])

  def test_sdk_location_gcs_source_file(self):
    staging_dir = self.make_temp_dir()
    sdk_location = 'gs://my-gcs-bucket/tarball.tar.gz'

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = sdk_location

    with mock.patch('.'.join([
        dependency.DataflowFileHandle.__module__,
        dependency.DataflowFileHandle.__name__,
        dependency.DataflowFileHandle.file_copy.__name__
    ])):
      self.assertEqual([names.DATAFLOW_SDK_TARBALL_FILE],
                       dependency.stage_job_resources(options))

  def test_sdk_location_gcs_wheel_file(self):
    staging_dir = self.make_temp_dir()
    sdk_filename = 'apache_beam-1.0.0-cp27-cp27mu-manylinux1_x86_64.whl'
    sdk_location = 'gs://my-gcs-bucket/' + sdk_filename

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = sdk_location

    with mock.patch('.'.join([
        dependency.DataflowFileHandle.__module__,
        dependency.DataflowFileHandle.__name__,
        dependency.DataflowFileHandle.file_copy.__name__
    ])):
      self.assertEqual([sdk_filename], dependency.stage_job_resources(options))

  def test_sdk_location_http(self):
    staging_dir = self.make_temp_dir()
    sdk_location = 'http://storage.googleapis.com/my-gcs-bucket/tarball.tar.gz'

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).sdk_location = sdk_location

    def file_download(dummy_self, _, to_path):
      with open(to_path, 'w') as f:
        f.write('Package content.')
      return to_path

    with mock.patch('.'.join([
        dependency.DataflowFileHandle.__module__,
        dependency.DataflowFileHandle.__name__,
        dependency.DataflowFileHandle.file_download.__name__
    ]), file_download):
      self.assertEqual([names.DATAFLOW_SDK_TARBALL_FILE],
                       dependency.stage_job_resources(options))

    tarball_path = os.path.join(staging_dir, names.DATAFLOW_SDK_TARBALL_FILE)
    with open(tarball_path) as f:
      self.assertEqual(f.read(), 'Package content.')

  def test_with_extra_packages(self):
    staging_dir = self.make_temp_dir()
    source_dir = self.make_temp_dir()
    self.create_temp_file(os.path.join(source_dir, 'abc.tar.gz'), 'nothing')
    self.create_temp_file(os.path.join(source_dir, 'xyz.tar.gz'), 'nothing')
    self.create_temp_file(os.path.join(source_dir, 'xyz2.tar'), 'nothing')
    self.create_temp_file(os.path.join(source_dir, 'whl.whl'), 'nothing')
    self.create_temp_file(
        os.path.join(source_dir, dependency.EXTRA_PACKAGES_FILE), 'nothing')

    options = PipelineOptions()
    options.view_as(GoogleCloudOptions).staging_location = staging_dir
    self.update_options(options)
    options.view_as(SetupOptions).extra_packages = [
        os.path.join(source_dir, 'abc.tar.gz'),
        os.path.join(source_dir, 'xyz.tar.gz'),
        os.path.join(source_dir, 'xyz2.tar'),
        os.path.join(source_dir, 'whl.whl'), 'gs://my-gcs-bucket/gcs.tar.gz'
    ]

    gcs_copied_files = []

    def file_copy(dummy_self, from_path, to_path):
      if from_path.startswith('gs://'):
        gcs_copied_files.append(from_path)
        _, from_name = os.path.split(from_path)
        if os.path.isdir(to_path):
          to_path = os.path.join(to_path, from_name)
        self.create_temp_file(to_path, 'nothing')
        logging.info('Fake copied GCS file: %s to %s', from_path, to_path)
      elif to_path.startswith('gs://'):
        logging.info('Faking file_copy(%s, %s)', from_path, to_path)
      else:
        shutil.copyfile(from_path, to_path)

    with mock.patch(
        '.'.join([
            dependency.DataflowFileHandle.__module__,
            dependency.DataflowFileHandle.__name__,
            dependency.DataflowFileHandle.file_copy.__name__
        ]), file_copy):
      self.assertEqual([
          'abc.tar.gz', 'xyz.tar.gz', 'xyz2.tar', 'whl.whl', 'gcs.tar.gz',
          dependency.EXTRA_PACKAGES_FILE
      ], dependency.stage_job_resources(options))
    with open(os.path.join(staging_dir, dependency.EXTRA_PACKAGES_FILE)) as f:
      self.assertEqual([
          'abc.tar.gz\n', 'xyz.tar.gz\n', 'xyz2.tar\n', 'whl.whl\n',
          'gcs.tar.gz\n'
      ], f.readlines())
    self.assertEqual(['gs://my-gcs-bucket/gcs.tar.gz'], gcs_copied_files)

  def test_with_extra_packages_missing_files(self):
    staging_dir = self.make_temp_dir()
    with self.assertRaises(RuntimeError) as cm:

      options = PipelineOptions()
      options.view_as(GoogleCloudOptions).staging_location = staging_dir
      self.update_options(options)
      options.view_as(SetupOptions).extra_packages = ['nosuchfile.tar.gz']

      dependency.stage_job_resources(options)
    self.assertEqual(
        cm.exception.args[0],
        'The file %s cannot be found. It was specified in the '
        '--extra_packages command line option.' % 'nosuchfile.tar.gz')

  def test_with_extra_packages_invalid_file_name(self):
    staging_dir = self.make_temp_dir()
    source_dir = self.make_temp_dir()
    self.create_temp_file(os.path.join(source_dir, 'abc.tgz'), 'nothing')
    with self.assertRaises(RuntimeError) as cm:
      options = PipelineOptions()
      options.view_as(GoogleCloudOptions).staging_location = staging_dir
      self.update_options(options)
      options.view_as(SetupOptions).extra_packages = [
          os.path.join(source_dir, 'abc.tgz')
      ]
      dependency.stage_job_resources(options)
    self.assertEqual(
        cm.exception.args[0],
        'The --extra_package option expects a full path ending with '
        '".tar", ".tar.gz", ".whl" or ".zip" '
        'instead of %s' % os.path.join(source_dir, 'abc.tgz'))


if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  unittest.main()
