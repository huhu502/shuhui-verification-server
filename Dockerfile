FROM aurorasystem/docker-shuhui-base-server
MAINTAINER Aurora System <it@aurora-system.com>

RUN yum install -y fftw

RUN \
  yum install -y epel-release && yum install -y python34 && yum remove -y epel-release && yum clean all && \
  ln -s /usr/bin/python3 /usr/local/bin/python3

# Python pip, numpy
ADD ./get-pip.py /tmp
RUN cd /tmp && \
  /usr/local/bin/python3 get-pip.py && \
  pip install numpy

ADD mkl_so/* /usr/local/lib/

Add asiv/* /usr/local/bin/

RUN useradd -ms /bin/bash deploy
USER deploy
RUN mkdir -p /home/deploy/app
WORKDIR /home/deploy/app
