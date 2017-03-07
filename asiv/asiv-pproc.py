######################
##### ASIV-PPROC #####
######################

# v0.3 (170115)
# Refined calculation for EW, EH, and timing margins. 
# Add an option to disable "adjust" by default
# Plot 1 UI instead of 0.5 UI for eye diagram
# Add Skew spec in "eye_parameter.txt" file
#
# Bug fixes:
# 1. Data not initialized for rd and wt case
# 2. Output trigger 

# v0.2 (170101)
# Fixed a bug for Yuxi's case
# Fixed a bug that causes mis-aligned eye diagram
# Add '--showplot' option

# v0.1 (161215)
# Read Aurora Raw output file
# Determine trigger points based on DQS waveform
# Define eye mask
# Calculate jitter
# Calculate eye height/width, and worst margin
# Generate eye diagram plot with eye mask
# Generate output files

# TO-DO:
# 

import logging
import os.path
import sys
import numpy as np
#import matplotlib.pyplot as plt

class Pproc:
    def __init__(self, projectDir, plotflag):
        self.use_adjust = 0
        self.plotflag = plotflag
        self.interfaces = []
        self.projectDir = projectDir
        self.configFile = self.projectDir + '/models/' + 'interface.md'
        self.readConfig(self.configFile)
        thisInterface = self.interfaces[-1]
        for thisByte in thisInterface.byte:
            rawfile = self.projectDir + '/data/byte' + thisByte.byteID + '_rd.raw'
            self.readRaw(thisByte, rawfile)
            self.procRaw(thisByte, rawfile)
            rawfile = self.projectDir + '/data/byte' + thisByte.byteID + '_wt.raw'
            self.readRaw(thisByte, rawfile)
            self.procRaw(thisByte, rawfile)
                
    def readConfig(self, file):
        self.modelPath = self.projectDir + '/models/'
        logging.debug('D001: Model Path is %s'%(self.modelPath))
        num_ddr = 0
        infile = open(file, 'r')
        for line in infile:
            if 'DDR {' in line:
                num_ddr = num_ddr + 1
                # Parse for ID, Type, Component information
                line_ID = next(infile)
                logging.debug ('Component ID is ' + line_ID)
                if not 'ID' in line_ID:
                    print ('E001: Cannot find DDR ID')
                else:
                    self.interfaces.append(DDR(line_ID.split()[1]))
                    thisInterface = self.interfaces[-1]
                    logging.debug ('Interface ID is ' + thisInterface.interfaceID)
                line_type = next(infile)
                if not 'Type' in line_type:
                    print ('E002: Cannot find DDR Type')
                else:
                    thisInterface.ddrType = line_type.split()[1]
                    clkfreq = (line_type.split()[2][:-3]).split('.')[0]
                    print(clkfreq)
                    thisInterface.dataRate = self.getDatarate(clkfreq)
                    logging.debug ('Interface data rate is ' + thisInterface.dataRate)
            if 'Byte {' in line:
                thisInterface.numByte += 1
                nextline = next(infile)
                byte_id = nextline.split()[-1]
                thisInterface.byte.append(Byte(byte_id))
                
        logging.debug('Number of DDR is ' + str(num_ddr))
        logging.debug('Number of Byte is ' + str(thisInterface.numByte))
        
    def readRaw(self, thisByte, rawfile):
        thisByte.wfm_time = []
        thisByte.wfm_dq0 = []
        thisByte.wfm_dq1 = []
        thisByte.wfm_dq2 = []
        thisByte.wfm_dq3 = []
        thisByte.wfm_dq4 = []
        thisByte.wfm_dq5 = []
        thisByte.wfm_dq6 = []
        thisByte.wfm_dq7 = []
        thisByte.wfm_dqsp = []
        thisByte.wfm_dqsn = []
        with open(rawfile, 'r') as f:
            flag = 0
            for line in f:
                if line.startswith('Values:'):
                    flag = 1
                    continue
                if flag == 1:   
                    if not len(line.split()) == 2:
                        print('Error reading raw file!')
                    timestep = line.split()[0]
                    thisByte.wfm_time.append(float(line.split()[1]))
                    nextline = next(f)
                    thisByte.wfm_dq0.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dq1.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dq2.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dq3.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dq4.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dq5.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dq6.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dq7.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dqsp.append(float(nextline.split()[0]))
                    nextline = next(f)
                    thisByte.wfm_dqsn.append(float(nextline.split()[0]))
                    for i in range(8): nextline = next(f)   # skip dq*_dig_out
            #print((thisByte.wfm_dqsn[0:10]))

    def procRaw(self, thisByte, rawfile):
        path, filename = os.path.split(rawfile)
        resultfolder = path + '/' + filename.split('.')[0]
        try:
            os.mkdir(resultfolder)
        except:
            pass
        wfm_dqs = []
        for i in range(len(thisByte.wfm_dqsp)):
            wfm_dqs.append(thisByte.wfm_dqsp[i] - thisByte.wfm_dqsn[i])
        datarate = int(self.interfaces[0].dataRate) * 1e6
        self.geteyemask(self.interfaces[0], self.interfaces[0].ddrType, datarate)
        vref = self.interfaces[0].vref
        self.eye(thisByte.wfm_dq0, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ0')
        self.eye(thisByte.wfm_dq1, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ1')
        self.eye(thisByte.wfm_dq2, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ2')
        self.eye(thisByte.wfm_dq3, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ3')
        self.eye(thisByte.wfm_dq4, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ4')
        self.eye(thisByte.wfm_dq5, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ5')
        self.eye(thisByte.wfm_dq6, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ6')
        self.eye(thisByte.wfm_dq7, wfm_dqs, thisByte.wfm_time, datarate, vref, self.interfaces[0].eyemask, resultfolder+'/DQ7')
        #print(resultfolder)
        
    def eye(self, dq, dqs, t, datarate, vref, eyemask, path):
        try:
            os.mkdir(path)
        except:
            pass
        ui = 1/datarate
        # interplate waveform
        dt = 1e-12
        t_intp = np.arange(t[0], t[-1]+1e-14, dt)
        dq = np.interp(t_intp, t, dq)
        dqs = np.interp(t_intp, t, dqs)
        #plt.plot(t_intp, dq)
        #plt.plot(t_intp, dqs)
        #plt.show()

        # build a 1d histrogram
        num_bins = 256
        [histo, histo_value] = np.histogram(dq, bins=num_bins)
        histo = histo.tolist()
        histo_value = histo_value.tolist()

        # find the range where data starts and stops in histogram
        for a in range(num_bins):
            if histo[a] != 0:
                start = a
                break
        for a in range(num_bins-1, 0, -1):
            if histo[a] != 0:
                stop = a
                break
        #plt.hist(dq, bins=256)
        #plt.show()

        # Determine the range of data, and define threshholds
        mid = int((start + stop) / 2) + 1
        high = histo_value[histo.index(max(histo[mid:stop]))+1]
        low = histo_value[histo.index(max(histo[start:mid]))+1]
        waverange = high - low
        mid = (high + low) / 2 
        lowthresh = .3 * waverange + low
        highthresh = .7 * waverange + low
        print('high, low, mid, range: ', high, low, mid, waverange)

        # Find the rise/fall edges of DQ
        dq_edges = self.edge(dq, mid, highthresh, lowthresh)
        #print (len(dq_edges), dq_edges)

        # Find the zero-crossing of DQS
        dqs_crossings = self.edge(dqs, 0, 0.1, -0.1)
        print ('number of trigger point: %d' % (len(dqs_crossings)))
        fout = open('trigger.txt', 'w')
        for t in dqs_crossings:
            fout.writelines('%.6e\n' % (t_intp[t]))
        fout.close()
        #for a in dqs_crossings: print ('%.6e'%(t_intp[a]))

        # Plot eye
        # Adjust for DQS delay
        dqs_delay = ui/2
        for i in range(len(dqs_crossings)):
            dqs_crossings[i] = dqs_crossings[i] + int(dqs_delay/dt)
        # Trigger DQ using DQS zero-crossing points
        eyedata = []    # 2D list to store eye diagram data, each list is a UI.
        for trigger in dqs_crossings:
            start = trigger - int((ui)/dt)
            stop = trigger + int((ui)/dt)
            #print (start, stop)
            if start < 0: start=0
            if stop > len(t_intp)-1: stop = len(t_intp)-1
            eyedata.append(dq[start:stop])
            
        # Find vref crossing (to determine jitter)
        vref_crossing = []
        xmax = 0
        xmin = 1e6
        for i in range(len(eyedata)):
            tmp = self.edge(eyedata[i], vref, vref+0.1, vref-0.1)
            if not tmp == []:
                for t in tmp:
                    if t > int(ui/dt) and t > xmax: 
                        xmax = t
                    if t > int(ui/dt) and t < xmin: 
                        xmin = t
                vref_crossing.append(tmp)
#       if xmin < 0.5*len(eyedata[0]):
#           xmin = xmin + len(eyedata[0])
        print('xmax, xmin: ', xmax, xmin)
        jitter = (xmax - xmin) * dt
        adjust = int(ui/dt) - xmax + int((xmax-xmin)/2)
        left_margin = eyemask[0][0] - (xmax*dt - ui)
        right_margin = xmin*dt - eyemask[3][0]
        print('Jitter: %.4e'%(jitter))
        print('left margin, right margin: ', left_margin, right_margin)
        # Adjust eye data to the center of UI
        if self.use_adjust == 0:
            adjust = 0
        eyedata = []
        for trigger in dqs_crossings:
            start = trigger - int((ui)/dt) - adjust
            stop = trigger + int((ui)/dt) - adjust
            if start < 0: start=0
            if stop > len(t_intp)-1: stop = len(t_intp)-1
            eyedata.append(dq[start:stop])
            if self.plotflag:
                plt.plot(dq[start:stop], color='blue')
        # find eye height, eye width
        min_high = 2*vref
        max_low = 0.0
        for eyedata_per_ui in eyedata:
            temp = eyedata_per_ui[int(eyemask[1][0]/dt):int(eyemask[2][0]/dt)]
            for data in temp:
                if data >= vref:
                    if data < min_high: min_high = data
                if data < vref:
                    if data > max_low:  max_low = data
        print('min_high, max_low: ', min_high, max_low)
        eyeheight = min_high - max_low
        eyewidth = ui - jitter
        top_margin = min_high - eyemask[1][1]
        bottom_margin = eyemask[5][1] - max_low
        print('eye height: ', eyeheight)
        print('eye width: ', eyewidth)
        # plot eye mask
        eyemask_t = []
        eyemask_v = []
        for point in eyemask:
            eyemask_t.append(int(point[0]/dt + adjust))
            eyemask_v.append(point[1])
        if self.plotflag:
            plt.plot(eyemask_t, eyemask_v, color='red', linewidth=2)        
            plt.savefig(path+'/eye.png')
            plt.close()
        
        # output to files
        f1 = open(path+'/trigger.txt', 'w')
        f1.write('UI: %.6e\n' % (ui))
        f1.write('Adjust: %.6e\n' % (adjust*dt))
        f1.write('Trigger: \n')
        for trigger in dqs_crossings:
             f1.write('%.6e\n' % ((trigger)*dt))
        f1.close()
        f2 = open(path+'/eye_parameter.txt', 'w')
        f2.write('ui: %.6e\n' % (ui))
        f2.write('minimun HIGH: %.6e\n' % (min_high))
        f2.write('maximum LOW: %.6e\n' % (max_low))
        f2.write('eye height: %.6e\n' % (eyeheight))
        f2.write('eye width: %.6e\n' % (eyewidth))
        f2.write('jitter: %.6e\n' % (jitter))
        f2.write('top margin: %.6e\n' % (top_margin))
        f2.write('bottom margin: %.6e\n' % (bottom_margin))
        f2.write('left margin: %.6e\n' % (left_margin))
        f2.write('right margin: %.6e\n' % (right_margin))
        f2.write('eye mask: \n')
        for i in range(6):
            f2.write('%.6e\t%.6e\n' % (eyemask[i][0], eyemask[i][1]))
        f2.write('skew spec DQ-DQS routing: %.6e\n' % (self.interfaces[0].skew_dq_dqs))
        f2.close()              

    def geteyemask(self, thisInterface, ddrtype, datarate):
        # set vref
        if ddrtype.lower() == 'ddr3':
            thisInterface.vref = 0.75
        elif ddrtype.lower() == 'ddr2':
            thisInterface.vref = 0.9
        else:
            print('Error: Cannot define vref.')
        # set eye mask
        if ddrtype.lower() == 'ddr3' or ddrtype.lower() == 'ddr2':
            vih = thisInterface.vref + 0.150
            vil = thisInterface.vref - 0.150
            if datarate == 800e6:
                tds = 125e-12
                tdh = 150e-12
            elif datarate == 1066e6:
                tds = 75e-12
                tdh = 100e-12
            elif datarate == 1333e6:
                tds = 30e-12
                tdh = 65e-12
            elif datarate == 1600e6:
                tds = 10e-12
                tdh = 45e-12
            else:
                print('Error: Cannot define eye mask.')
        ui = 1/datarate
        thisInterface.eyemask.append([ui-tds-0.1*ui, thisInterface.vref])
        thisInterface.eyemask.append([ui-tds, vih])
        thisInterface.eyemask.append([ui+tdh, vih])
        thisInterface.eyemask.append([ui+tdh+0.1*ui, thisInterface.vref])
        thisInterface.eyemask.append([ui+tdh, vil])
        thisInterface.eyemask.append([ui-tds, vil])
        thisInterface.eyemask.append([ui-tds-0.1*ui, thisInterface.vref])   
        # set DQ-DQS skew (allocation 2% of UI for routing error)
        thisInterface.skew_dq_dqs = ui * 0.02

    def edge(self, data, mid, high, low):
        # Find Edges
        var1 = []
        data = np.asarray(data)
        gtmid = data > mid
        gthigh = data > high
        gtlow = data < low
        if len(gtmid) == 0: return []
        #print('size of gtmid', len(gtmid))
        temp = gtmid[0]
        cross = False

        for a in range(len(gtmid)):
            if cross == False:
                if temp != gtmid[a]:
                    temp = gtmid[a]
                    var1.append(a)
                    cross = True
            else:
                if cross == gthigh[a] or cross == gtlow[a]:
                    cross = False
        return var1

    def getDatarate(self, clkfreq):
        clkfreq = float(clkfreq)
        if clkfreq > 800/2*0.95 and clkfreq < 800/2*1.05:
            return '800'
        if clkfreq > 1066/2*0.95 and clkfreq < 1066/2*1.05:
            return '1066'
        if clkfreq > 1333/2*0.95 and clkfreq < 1333/2*1.05:
            return '1333'
        if clkfreq > 1600/2*0.95 and clkfreq < 1600/2*1.05:
            return '1600'
        if clkfreq > 1866/2*0.95 and clkfreq < 1866/2*1.05:
            return '1866'
        
class DDR:
    def __init__ (self, id):
        self.interfaceID = id
        self.ddrType = ''
        self.dateRate = ''
        self.comps = []
        self.byte = []
        self.ctrl = []
        self.numByte = 0
        self.eyemask = []
        self.vref = 0.0
        self.skew_dq_dqs = 0

class Byte:
    def __init__ (self, id):
        self.byteID = id
        self.wfm_time = []
        self.wfm_dq0 = []
        self.wfm_dq1 = []
        self.wfm_dq2 = []
        self.wfm_dq3 = []
        self.wfm_dq4 = []
        self.wfm_dq5 = []
        self.wfm_dq6 = []
        self.wfm_dq7 = []
        self.wfm_dqsp = []
        self.wfm_dqsn = []
        self.wfm_alldq_time = []
        self.wfm_alldq_dq = []
        self.wfm_alldq_dqs = []
        
class Signal:
    def __init__ (self, id):
        self.sigID = id
        self.socPin = ''
        self.ddrPin = []
        
if __name__ == "__main__":
    #logging.basicConfig(level=logging.DEBUG)    # uncomment this line to output debug info
    if not (len(sys.argv) == 2 or len(sys.argv) == 3):
        print('Error! Usage: python3 pproc.py <path_to_interface_folder>')
        exit()
    plotflag = 0
    if '--showplot' in sys.argv:
        plotflag = 1
    projectDir = os.path.abspath(sys.argv[1])
    thispproc = Pproc(projectDir, plotflag)
    
