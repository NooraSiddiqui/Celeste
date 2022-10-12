#!/usr/bin/env python
# Copyright 2018 Illumina, Inc. All rights reserved.
#
# This file contains confidential and proprietary information of the Edico Genome
# Corporation and is protected under the U.S. and international copyright and other
# intellectual property laws.
#
# $Id$
# $Author$
# $Change$
# $DateTime$
#
# Wrapper to start processes in the background and catch any signals used to
# terminate the process.  Multiple processes are executed sequentially.  Stops dragen
# processes gracefully by running dragen_reset when dragen_board is in use.
#

from __future__ import print_function
from builtins import filter
from builtins import str
from builtins import object
import copy
import datetime
import glob
import os
import resource
import shutil
import subprocess
import sys
import time
import uuid
import six

DRAGEN_PATH = '/opt/edico/bin/dragen'
D_HAUL_UTIL = 'python /root/quickstart/d_haul'
DRAGEN_LOG_FILE_NAME = 'dragen_log_%d.txt'
DEFAULT_DATA_FOLDER = '/ephemeral/'
CLOUD_SPILL_FOLDER = '/ephemeral/'
FPGA_DOWNLOAD_STATUS_FILE = DEFAULT_DATA_FOLDER + 'fpga_dl_stat.txt'
REDIRECT_OUTPUT_CMD_SUFFIX = '> %s 2>&1'

#########################################################################################
# printf - Print to stdout with flush
#
def printf(msg):
    print(msg, file=sys.stdout)
    sys.stdout.flush()


#########################################################################################
# get_s3_bucket_key - Extract S3 bucket and key from input URL if it is S3 bucket
#   Input s3_url expected format s3://bucket/key
#   Return a tuple: (s3_found, bucket, key), i.e. (False, None, None) if not found
#
def get_s3_bucket_key(s3_url):
    try:
        s3_url = s3_url.strip()
        if s3_url.find('s3://') != 0:
            raise Exception('Not S3 URL - could not get bucket and key')
        # Extract the bucket and key
        s3_path = s3_url.replace('//', '/')
        s3_bucket = s3_path.split('/')[1]
        s3_key = '/'.join(s3_path.split('/')[2:])
        return True, s3_bucket, s3_key
    # Confirm S3 URL
    except Exception:
        return False, None,  None

#########################################################################################
# exec_cmd - Execute command and return [stdout/stderr, exitstatus]
#
def exec_cmd(cmd, shell=True):
    printf("Executing %s" % cmd.strip())
    if not shell:
        p = subprocess.Popen(cmd.split())
    else:
        p = subprocess.Popen(cmd, shell=True, executable='/bin/bash')
    err = p.wait()
    return err

#########################################################################################
# DragenJob - Dragen Job execution object
#
class DragenJob(object):

    def __init__(self, dragen_args):
        self.orig_args = dragen_args
        self.new_args = copy.copy(dragen_args)

        # Inputs needed for downloading
        self.ref_dir = None             # Create local directory to download reference
        self.input_dir = None           # Create local directory for Dragen input info

        self.ref_s3_url = None          # Determine from the -r or --ref-dir option
        self.ref_s3_index = -1

        self.fastq_list_url = None      # Determine from the --fastq-list option
        self.fastq_list_index = -1

        self.cram_input_url = None      # Determine from the --cram-input option
        self.cram_input_index = -1

        self.vc_tgt_bed_url = None      # Determine from the --vc-target-bed option
        self.vc_tgt_bed_index = -1

        self.vc_depth_url = None        # Determine from the --vc-depth-intervals-bed option
        self.vc_depth_index = -1

        self.qc_coverage_region1_url = None # Determine from the --qc-coverage-region-1 option
        self.qc_coverage_region1_index = -1

        self.qc_coverage_region2_url = None # Determine from the --qc-coverage-region-2 option
        self.qc_coverage_region2_index = -1

        self.qc_coverage_region3_url = None # Determine from the --qc-coverage-region-3 option
        self.qc_coverage_region3_index = -1

        self.qc_cross_cont_vcf_url = None # Determine from the --qc-cross-cont-vcf option
        self.qc_cross_cont_vcf_index = -1

        # Output info
        self.output_s3_url = None       # Determine from the --output-directory field
        self.output_s3_index = -1
        self.output_dir = None          # Create local output directory for current dragen process

        # Run-time variables
        self.input_dir = None          # Create local output directory for current dragen process
        self.process_start_time = None  # Process start time
        self.process_end_time = None    # Process end time
        self.global_exit_code = 0       # Global exit code. If any process fails then we exit with a non-zero status

        self.set_resource_limits()
        self.parse_download_args()

    ########################################################################################
    # parse_download_args - Parse the command line looking for these specific options which
    # are used to download S3 files
    #
    def parse_download_args(self):
        # -r or --reference: S3 URL for reference HT
        (self.ref_s3_url, self.ref_s3_index) = self.set_options_url_idx(self.ref_s3_url, self.ref_s3_index, '-r', '--ref-dir')
        # --output-directory: S3 URL for output location
        (self.output_s3_url, self.output_s3_index) = self.set_options_url_idx(self.output_s3_url, self.output_s3_index, '--output-directory')
        # --fastq-list: URL (http or s3) for fastq list CSV file
        (self.fastq_list_url, self.fastq_list_index) = self.set_options_url_idx(self.fastq_list_url, self.fastq_list_index, '--fastq-list')
        # --cram-input: URL (http or s3) for cram file
        (self.cram_input_url, self.cram_input_index) = self.set_options_url_idx(self.cram_input_url, self.cram_input_index, '--cram-input')
        # --vc-target-bed: URL for the VC target bed
        (self.vc_tgt_bed_url, self.vc_tgt_bed_index) = self.set_options_url_idx(self.vc_tgt_bed_url, self.vc_tgt_bed_index, '--vc-target-bed')
        # --vc-depth-intervals-bed: URL for the VC depth intervals
        (self.vc_depth_url, self.vc_depth_index) = self.set_options_url_idx(self.vc_depth_url, self.vc_depth_index, '--vc-depth-intervals-bed')
        # --qc-coverage-region-1: URL for qc_coverage_region
        (self.qc_coverage_region1_url, self.qc_coverage_region1_index) = self.set_options_url_idx(self.qc_coverage_region1_url, self.qc_coverage_region1_index, '--qc-coverage-region-1')
        # --qc-coverage-region-2: URL for qc_coverage_region
        (self.qc_coverage_region2_url, self.qc_coverage_region2_index) = self.set_options_url_idx(self.qc_coverage_region2_url, self.qc_coverage_region2_index, '--qc-coverage-region-2')
        # --qc-coverage-region-3: URL for qc_coverage_region
        (self.qc_coverage_region3_url, self.qc_coverage_region3_index) = self.set_options_url_idx(self.qc_coverage_region3_url, self.qc_coverage_region3_index, '--qc-coverage-region-3')   
        # --qc-cross-cont-vcf: URL for qc cross contamination VCF
        (self.qc_cross_cont_vcf_url, self.qc_cross_cont_vcf_index) = self.set_options_url_idx(self.qc_cross_cont_vcf_url, self.qc_cross_cont_vcf_index, '--qc-cross-cont-vcf')

    #########################################################################################
    # set_options_url_idx - Set option's url and index if found in args
    #
    def set_options_url_idx(self, opt_url, opt_index, *argv):
        for arg in argv:
            try:
                opt_no = self.orig_args.index(arg)
                opt_url = self.orig_args[opt_no + 1]
                opt_index = opt_no + 1
                break
            except ValueError:
                continue
        return opt_url, opt_index

   ########################################################################################
    # set_resource_limits - Set resource limits prior.
    #
    def set_resource_limits(self):
        # Set resource limits based on values in /etc/security.d/limits.d/99-edico.conf
        edico_limits = "/etc/security/limits.d/99-edico.conf"
        rlimit = {}
        if os.path.exists(edico_limits):
            with open(edico_limits, 'r') as limitsfd:
                for line in limitsfd:
                    fields = line.split()
                    if fields[0] == '*' and fields[2] in ['nproc', 'nofile', 'stack']:
                        res = eval("resource.RLIMIT_%s" % fields[2].upper())
                        if fields[3] == "unlimited":
                            rlimit[res] = resource.RLIM_INFINITY
                        else:
                            if fields[2] == 'stack':
                                # limits.conf file is in KB, setrlimit command takes bytes
                                rlimit[res] = int(fields[3]) * 1024
                            else:
                                rlimit[res] = int(fields[3])
        else:
            rlimit[resource.RLIMIT_NPROC] = 16384
            rlimit[resource.RLIMIT_NOFILE] = 65535
            rlimit[resource.RLIMIT_STACK] = 10240 * 1024

        for res, limit in six.iteritems(rlimit):
            printf("Setting resource %s to %s" % (res, limit))
            try:
                resource.setrlimit(res, (limit, limit))
            except Exception as e:
                printf("Could not set resource ID %s to hard/soft limit %s (error=%s)" \
                      % (res, limit, e))

    ########################################################################################
    # copy_var_log_dragen_files - Copy over the most recent /var/log/dragen files to output dir
    #
    def copy_var_log_dragen_files(self):
        self.copy_file("/var/log/dragen/dragen_run*.log")
        self.copy_file("/var/log/dragen/hang_diag*.txt")
        self.copy_file("/var/log/dragen/pstack*.log")
        self.copy_file("/var/log/dragen/dragen_info*.log")
        self.copy_file("/var/log/dragen/dragen_replay*.json")

    def copy_file(self, path):
        files = list(filter(os.path.isfile, glob.glob(path)))
        if files:
            newest_file = sorted(files, key=lambda x: os.path.getmtime(x), reverse=True)[0]
            shutil.copy2(newest_file, self.output_dir)

    ########################################################################################
    # download_dragen_fpga - Perform the 'partial reconfig' to download binary image to FPGA
    #   NOTE: Should ONLY be called when self.FPGA_DOWNLOAD_STATUS_FILE does not exist
    #
    def download_dragen_fpga(self):
        exit_code = \
            exec_cmd("/opt/edico/bin/dragen --partial-reconfig DNA-MAPPER --ignore-version-check true -Z 0")

        if not exit_code:
            # PR complete success. Write '1' into status file
            with open(FPGA_DOWNLOAD_STATUS_FILE, 'w') as f:
                f.write('1')
            printf('Completed Partial Reconfig for FPGA')
        else:
            # Error!
            printf('Could not do initial Partial Reconfig program for FPGA')

    ########################################################################################
    # check_board_state - Check dragen_board state and run reset (if needed)
    #
    def check_board_state(self):
        exit_code = exec_cmd("/opt/edico/bin/dragen_reset -cv")
        if exit_code:
            printf("Dragen board is in a bad state - running dragen_reset")
            exec_cmd("/opt/edico/bin/dragen_reset")

    ########################################################################################
    # exec_url_download - Download a file from the given URL to the target directory
    #
    def exec_url_download(self, url, target_dir):
        dl_cmd = '{bin} --mode download --url {url} --path {target}'.format(
            bin=D_HAUL_UTIL,
            url=url,
            target=target_dir)
        return exec_cmd(dl_cmd)

    ########################################################################################
    # download_s3_object: Download an object from S3 bucket/key to spefific target file path
    #
    def download_s3_object(self, bucket, key, target_path):
        dl_cmd = '{bin} --mode download --bucket {bucket} --key {key} --path {target}'.format(
            bin=D_HAUL_UTIL,
            bucket=bucket,
            key=key,
            target=target_path)
        return exec_cmd(dl_cmd)

    ########################################################################################
    # download_inputs: Download specific Dragen inputs needed from provided URLs, and
    # replace them with a local path, i.e. fastq_list, bed files, etc.
    #
    def download_inputs(self):
        if not self.input_dir:
            self.input_dir = DEFAULT_DATA_FOLDER + 'inputs/'

        # -- fastq list file download
        self.download_input(self.fastq_list_url, self.fastq_list_index)
        # -- cram file download
        self.download_input(self.cram_input_url, self.cram_input_index)
        # -- VC target bed download
        self.download_input(self.vc_tgt_bed_url, self.vc_tgt_bed_index)
        # -- VC Depth file download
        self.download_input(self.vc_depth_url, self.vc_depth_index)
        # -- qc-coverage-regions1 file download
        self.download_input(self.qc_coverage_region1_url, self.qc_coverage_region1_index)
        # -- qc-coverage-regions2 file download
        self.download_input(self.qc_coverage_region2_url, self.qc_coverage_region2_index)
        # -- qc-coverage-regions3 file download
        self.download_input(self.qc_coverage_region3_url, self.qc_coverage_region3_index)
        # -- qc_cross_cont_vcf_url file download
        self.download_input(self.qc_cross_cont_vcf_url, self.qc_cross_cont_vcf_index)

    def download_input(self, url, idx):
        if url:
            filename = url.split('?')[0].split('/')[-1]
            target_path = self.input_dir + str(filename)

            s3_valid, s3_bucket, s3_key = get_s3_bucket_key(url)
            if s3_valid:
                exit_code = self.download_s3_object(s3_bucket, s3_key, target_path)
            else:
                # Try to download using http
                exit_code = self.exec_url_download(url, self.input_dir)
            if exit_code:
                printf('Error: Failure downloading from S3. Exiting with code %d' % exit_code)
                sys.exit(exit_code)

            self.new_args[idx] = target_path

    ########################################################################################
    # download_ref_tables: Download directory of reference hash tables using the S3
    #  "directory" prefix self.ref_s3_url should be in format s3://bucket/ref_objects_prefix
    #
    def download_ref_tables(self):
        if not self.ref_s3_url:
            printf('Warning: No reference HT directory URL specified!')
        else:
            # Generate the params to download the HT based on URL s3://bucket/key
            s3_valid, s3_bucket, s3_key = get_s3_bucket_key(self.ref_s3_url)

            if not s3_valid or not s3_key or not s3_bucket:
                printf('Error: could not get S3 bucket and key info from specified URL %s' % self.ref_s3_url)
                sys.exit(1)

            self.download_s3_object(s3_bucket, s3_key, DEFAULT_DATA_FOLDER)

            self.ref_dir = DEFAULT_DATA_FOLDER + s3_key
            self.new_args[self.ref_s3_index] = self.ref_dir

    ########################################################################################
    # Upload the results of the job to the desired bucket location
    #    output_s3_url should be in format s3://bucket/output_objects_prefix
    # Returns:
    #    Nothing if success
    def upload_job_outputs(self):
        if not self.output_s3_url:
            printf('Error: Output S3 location not specified!')
            return

        # Generate the command to upload the results
        s3_valid, s3_bucket, s3_key = get_s3_bucket_key(self.output_s3_url)

        if not s3_valid or not s3_key or not s3_bucket:
            printf('Error: could not get S3 bucket and key info from specified URL %s' % self.output_s3_url)
            sys.exit(1)

        ul_cmd = '{bin} --mode upload --bucket {bucket} --key {key} --path {file} -s'.format(
            bin=D_HAUL_UTIL,
            bucket=s3_bucket,
            key=s3_key,
            file=self.output_dir.rstrip('/'))

        exit_code = exec_cmd(ul_cmd)
        if exit_code:
            printf('Error: Failure uploading outputs. Exiting with code %d' % exit_code)
            sys.exit(exit_code)

    ########################################################################################
    # create_output_dir - Checks for existance of outdir and creates it if necessary,
    # and saves it to internal self.output_dir variable
    #
    def create_output_dir(self):
        if not self.output_dir or not os.path.exists(self.output_dir):
            self.output_dir = DEFAULT_DATA_FOLDER + str(uuid.uuid4())
            printf("Output directory does not exist - creating %s" % self.output_dir)
            try:
                os.makedirs(self.output_dir)
            except os.error:
                # dragen execution will fail
                printf("Error: Could not create output_directory %s" % self.output_dir)
                sys.exit(1)
        else:
            printf("Output directory %s already exists - Skip creating." % self.output_dir)

        # Add or replace the output directory in the dragen parameters
        if self.output_s3_index >= 0:
            self.new_args[self.output_s3_index] = self.output_dir

    ########################################################################################
    # run_job - Create the command line for the given process, launch it, and monitor
    # it for completion.
    #
    def run_job(self):
        # Check if FPGA image download is needed
        if not os.path.isfile(FPGA_DOWNLOAD_STATUS_FILE):
            self.download_dragen_fpga()

        # If board is in bad state, run dragen_reset before next process starts
        self.check_board_state()

        # Setup unique output directory
        self.create_output_dir()

        # Add some internally defined parameters
        self.new_args.extend(
            ['--output_status_file', self.output_dir + '/job-speedometer.log']
        )
        self.new_args.extend(
            ['--intermediate-results-dir', CLOUD_SPILL_FOLDER]
        )
        self.new_args.extend(
            ['--lic-no-print']
        )

        # expand the Dragen args to construct the full command
        dragen_opts = ' '.join(self.new_args)

        # Construct the 'main' Dragen command
        dragen_cmd = "%s %s " % (DRAGEN_PATH, dragen_opts)

        # Save the Dragen output to a file instead of stdout
        output_log_path = self.output_dir + '/' + DRAGEN_LOG_FILE_NAME % round(time.time())
        redirect_cmd = REDIRECT_OUTPUT_CMD_SUFFIX % output_log_path
        dragen_cmd = "%s %s" % (dragen_cmd, redirect_cmd)

        # Run the Dragen process
        self.process_start_time = datetime.datetime.utcnow()
        exit_code = exec_cmd(dragen_cmd)

        # Upload the results to S3 output bucket
        self.upload_job_outputs()

        # Delete the output results directory, i.e. /staging/<uuid4>
        # NOTE: Do not delete the reference directory enable re-use with another job
        rm_out_path = self.output_dir
        printf("Removing Output dir %s" % rm_out_path)
        shutil.rmtree(rm_out_path, ignore_errors=True)

        # Delete fastq list or cram input
        printf("Removing .fastq_list.csv or .cram input")
        fastq_list = glob.glob(self.input_dir + '*.fastq_list.csv')
        if len(fastq_list) > 0:
            os.remove(fastq_list[0])
            printf("Deleted: " + fastq_list[0])

        cram = glob.glob(self.input_dir + '*.cram')
        if len(cram) > 0:
            os.remove(cram[0])
            print("Deleted: " + cram[0])

        # glob.glob(self.input_dir + '*.fastq.gz') #VICKY CONFIRM FASTQ.GZs are streamed, not downloaded

        # Handle error code
        if exit_code:
            self.copy_var_log_dragen_files()
            self.global_exit_code = exit_code
            if self.global_exit_code > 128 or self.global_exit_code < 0:
                if self.global_exit_code > 128:
                    signum = self.global_exit_code - 128
                else:
                    signum = -self.global_exit_code
                printf("Job terminated due to signal %s" % signum)

        self.process_end_time = datetime.datetime.utcnow()

    ########################################################################################
    # run - Run all processes in the job.
    #
    def run(self):
        try:
            self.run_job()
            printf("Job is exiting with code %s" % self.global_exit_code)
            sys.exit(self.global_exit_code)

        except SystemExit as inst:
            if inst != 0:  # System exit with exit code 0 is OK
                printf("Caught SystemExit: Exiting with status %s" % inst)
                sys.exit(inst)
            else:
                printf("Caught SystemExit: Exiting normally")

        except:
            # Log abnormal exists
            printf("Unhandled exception in dragen_qs: %s" % sys.exc_info()[0])
            sys.exit(1)

        delta = self.process_end_time - self.process_start_time
        printf("Job ran for %02d:%02d:%02d" % (delta.seconds//3600, delta.seconds//60 % 60, delta.seconds % 60))
        sys.exit(0)


#########################################################################################
# main
#
def main():
    # import ipdb; ipdb.set_trace()
    # Configure command line arguments
    dragen_args = sys.argv[1:]

    # Debug print (remove later)
    printf("[DEBUG] Dragen input commands: %s" % ' '.join(dragen_args))

    dragen_job = DragenJob(dragen_args)

    printf('Downloading reference files')
    dragen_job.download_ref_tables()

    printf('Downloading misc inputs (csv, bed)')
    dragen_job.download_inputs()

    printf('Run Analysis job')
    dragen_job.run()


if __name__ == "__main__":
    main()
