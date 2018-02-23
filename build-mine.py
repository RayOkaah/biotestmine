#!/usr/bin/python3

import argparse
import logging

import coloredlogs

import interminepy.mine as imm
import interminepy.project as imp
import interminepy.utils as imu


# MAIN
logger = logging.getLogger('build-mine.py')
coloredlogs.install(level='DEBUG')

parser = argparse.ArgumentParser('Build the mine')

parser.add_argument(
    'mine_properties_path', help="path to the mine's properties file, e.g. ~/.intermine/biotestmine.properties")

parser.add_argument(
    'checkpoints_path',
    help='The directory in which to place database checkpoint dumps when the dump="true" flag is set in the <source>'
         ' entry of the project.xml')

parser.add_argument(
    '--dry-run', action='store_true', default=False,
    help='Don''t actually build anything, just show the commands that would be executed')

args = parser.parse_args()

imu.check_path_exists(args.mine_properties_path)
imu.check_path_exists(args.checkpoints_path)
imu.check_path_exists('project.xml')

options = {'dry-run': args.dry_run, 'run-in-shell': False}

with open('project.xml') as f:
    project = imp.Project(f)

sources = project.sources

for source in sources.values():
    logger.debug('Found source %s in project.xml', source.name)

db_config = imm.get_db_config(args.mine_properties_path, 'production')

if imu.run_return_rc(
        "psql -lqt | cut -d \| -f 1 | grep -qw %s" % db_config['name'], {**options, **{'run-in-shell': True}}) == 0:
    imu.run_on_db(['dropdb', db_config['name']], db_config, options)

imu.run_on_db(['createdb', '-E', 'UTF8', db_config['name']], db_config, options)

last_checkpoint_path = imm.get_last_checkpoint_path(project, args.checkpoints_path)
if last_checkpoint_path is not None:
    logger.info('Restoring from last found checkpoint %s', last_checkpoint_path)

    imu.run_on_db(['pg_restore', '-1', '-d', db_config['name'], last_checkpoint_path], db_config, options)

    source_name = imm.split_checkpoint_path(last_checkpoint_path)[2]
    logger.info('Resuming after source %s', source_name)
    keys = list(project.sources.keys())

    next_source_index = keys.index(source_name) + 1

    if next_source_index < len(sources):
        keys = keys[next_source_index:]
        for source_name in keys:
            imm.integrate_source(sources[source_name], db_config, args.checkpoints_path, options)

else:
    logger.info('No previous checkpoint found, starting build from the beginning')

    imu.run(['./gradlew', 'buildDB'], options)
    imu.run(['./gradlew', 'buildUserDB'], options)
    imu.run(['./gradlew', 'loadDefaultTemplates'], options)

    for source in sources.values():
        imm.integrate_source(source, db_config, args.checkpoints_path, options)

imu.run(['./gradlew', 'postprocess', '--no-daemon'], options)

logger.info('Finished. Now run "./gradlew tomcatStartWar"')
