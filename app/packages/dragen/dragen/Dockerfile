# DRAGEN Quickstart Docker image generator --
FROM centos:centos7
RUN rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm

# Install Basic packages needed for Dragen
RUN yum -y install \
  perl \
  sos \
  coreutils \
  gdb \
  time \
  systemd-libs \
  bzip2-libs \
  R \
  ca-certificates \
  ipmitool \
  smartmontools \
  rsync && \
  yum clean all && \
  mkdir -m777 -p /var/log/dragen /var/run/dragen

#########################################################
# Now install the Edico WFMS "Wrapper" functions

# Install necessary standard packages
# Note: 'easy_install' used to workaround docker/kernel issue (https://github.com/moby/moby/issues/12327)
RUN yum -y install \
  python-devel \
  python-pip \
  tree && \
  yum clean all && \
  pip install --upgrade "pip < 21.0" && \
  pip install future && \
  pip install six && \
  pip install requests && \
  pip install boto3

# Install d_haul and dragen_job_execute wrapper functions and associated packages
RUN mkdir -p /root/quickstart/scheduler && \
    touch /root/quickstart/scheduler/__init__.py
COPY src/d_haul src/dragen_qs.py /root/quickstart/
COPY src/scheduler/aws_utils.py src/scheduler/logger.py src/scheduler/scheduler_utils.py  \
    /root/quickstart/scheduler/

# Landing directory should be where the run script is located
WORKDIR "/root/quickstart/"

# Debug print of container's directories
RUN tree /root/quickstart/

# Default behaviour. Over-ride with --entrypoint on docker run cmd line
ENTRYPOINT ["/root/quickstart/dragen_qs.py"]
CMD []
