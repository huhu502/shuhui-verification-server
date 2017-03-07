######################
##### AGIV-SPGEN #####
######################

# v0.5 (170120)
# Parse Xilinx IBIS model

# v0.42 (170207)
# Handle the quotation marks ("") in component names from the interface file
# Remove the @BOMpart keyword from component names to get the actual name

# v0.41 (161205)
# Compatible with Telechips parts. 

# v0.4 (161124)
# Change Usage: python3 spgen.py <path_to_interface_folder>. No more iterate of every folder in "Result".
# Parse Enable (active high/low) from IBIS file and used in the deck.
# Generate write deck.

# v0.31 (161117)
# Parse IBIS for receiver model (support type: I/O, Input).
# Implemented Rx model in the deck. Support with/without ODT.
# Parse IBIS for Model Type (I/O, Input, 3-state, etc).
# Enhance to support 3-state buffer.
# Enable digital output of Rx.
# Change back to absolute path.
# Double quotes for file name and model name.
# Include pin parasitics for receiver model.
# Don't use parameters in LFSR statement for better compatibility. 
# Probe (print) all DQ, DQS signal at rx_pad. Also output digital output from rx model. 

# v0.2 (161103)
# Updated script usage: python3 spgen.py <path_to_result_folder>
# Iterate through all interfaces in "result" folder
# Support IBIS file with multiple components. Able to match the component name specified in interface.md.
# Parse the package RLC for specific component. And use this value in the SPICE deck.
# Parse the RLC parasitics for each pin if such information is available in IBIS.
# Implemented Pin parasitics in the deck.
# Change "Models" to "models".
# Use abosolute path for included files in the deck.
# Able to parse scale prefix, e.g. 11m = 0.011, 100pF = 100e-12
# Bug fix:
#   - Typo "0 BYTE0" -> "+ BYTE0"
#   - Use double quotes (") instead of (') for model names and filenames for IBIS
#   - Change "ground" to "0" in socpkg and ddrpkg subckt
#   - Remove unused nodes from .probe/.print statement

# v0.1 (160930)
# Parse interface.md and build database
# Parse IBIS file and define the model for each pin
# Generate read deck

# TO-DO:
# - generate deck for address and control signals
# - DONE - include pin parasitics for receiver model
# - DONE - parse receiver model from IBIS (this is tricky...) For now, generic receiver model is used. Need to study the impact.
# - DONE - generate write deck
# - DONE - parse the "component" information from IBIS
# - DONE - parse Pin RLC from IBIS and include in the deck
# - DONE - parse Package RLC from IBIS


# Known limitations:
# - Assumed same IBIS model for 8-DQ (mostly true).
# - Assume the order of pin for DQ and DQS are the same in interface.md and BYTE*.sp


import logging
import os.path
import sys
import re
import shlex
from collections import defaultdict

class Design:
    def __init__ (self, file):
        self.interfaces = []
        self.configFile = file
        self.readConfig(self.configFile)
        self.generateByteDeck('rd')
        logging.debug('Read deck generated sucessfully.')
        self.generateByteDeck('wt')
        logging.debug('Write deck generated sucessfully.')
    
    def readConfig(self, file):
        self.modelPath = os.path.dirname(file)
        logging.debug('D001: Model Path is %s'%(self.modelPath))
        num_ddr = 0
        infile = open(file, 'r')
        for line in infile:
            if 'DDR {' in line:
                num_ddr = num_ddr + 1

                # Parse for ID, Type, Component information
                line_ID = next(infile)
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
                line_comp = next(infile)
                if not 'Components {' in line_comp:
                    print ('E003: Cannot find DDR Components')
                else:
                    line_comp = next(infile)    #skip the "Components {" line
                    while not '}' in line_comp:
                        if 'NameModel' in line_comp:
                            words = shlex.split(line_comp)
                            thisInterface.comps.append(Component(words[1], words[2].replace("@BOMpart",""), words[3], words[4]))
                            if len(line_comp.split()) > 5:
                                if line_comp.split()[5] == 'DIMM':
                                    thisInterface.comps[-1].isDIMM = 1
                                    print('%s is DIMM.' % (thisInterface.comps[-1].compID))
                        line_comp = next(infile)
                        logging.debug (thisInterface.comps[-1].compID)
                        logging.debug (thisInterface.comps[-1].compPart)
                        logging.debug (thisInterface.comps[-1].compModelFile)
                        logging.debug (thisInterface.comps[-1].compManufacture)
                nextline = next(infile)
                
                # Process IBIS file for model_selector <-> model name mapping 
                self.parseIbis(thisInterface)
                print('Finish parsing IBIS file.')
                #logging.debug(thisInterface.comps[1].compIbis.ibis_selector2model['DM'])

                # Parse for Byte
                if not 'Byte {' in nextline:
                    print ('E004: Cannot find DDR Byte')
                else:
                    while 'Byte {' in nextline:
                        line_byte = next(infile)
                        if not 'ID' in line_byte:
                            print ('E005: Error in reading DDR Byte ID')
                        else:
                            thisInterface.byte.append(Byte(line_byte.split()[-1]))
                            thisInterface.numByte += 1
                            thisByte = thisInterface.byte[-1]
                            logging.debug ('D010: Byte ID is ' + thisByte.byteID)
                        line_byte = next(infile)
                        if not 'SoC' in line_byte:
                            print ('E006: Error in reading DDR Byte SoC component')
                        else:
                            thisByte.socComp = line_byte.split()[-1]
                            logging.debug ('D011: SoC comp is ' + thisByte.socComp)
                        line_byte = next(infile)
                        if not 'SoC_Pin_DQ' in line_byte:
                            print ('E007: Error in reading DDR Byte SoC DQ Pin')
                        elif not len(line_byte.split()) == 9:
                            print ('E008: Error in reading DDR Byte SoC DQ Pin: Number of pin is not 8')
                        else:
                            thisByte.dq0.socPin = line_byte.split()[1]
                            thisByte.dq1.socPin = line_byte.split()[2]
                            thisByte.dq2.socPin = line_byte.split()[3]
                            thisByte.dq3.socPin = line_byte.split()[4]
                            thisByte.dq4.socPin = line_byte.split()[5]
                            thisByte.dq5.socPin = line_byte.split()[6]
                            thisByte.dq6.socPin = line_byte.split()[7]
                            thisByte.dq7.socPin = line_byte.split()[8]
                            thisByte.dq0.socModelTx, thisByte.dq0.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq0.socPin)
                            thisByte.dq1.socModelTx, thisByte.dq1.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq1.socPin)
                            thisByte.dq2.socModelTx, thisByte.dq2.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq2.socPin)
                            thisByte.dq3.socModelTx, thisByte.dq3.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq3.socPin)
                            thisByte.dq4.socModelTx, thisByte.dq4.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq4.socPin)
                            thisByte.dq5.socModelTx, thisByte.dq5.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq5.socPin)
                            thisByte.dq6.socModelTx, thisByte.dq6.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq6.socPin)
                            thisByte.dq7.socModelTx, thisByte.dq7.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dq7.socPin)
                        line_byte = next(infile)
                        if not 'SoC_Pin_DQS' in line_byte:
                            print ('E009: Error in reading DDR Byte SoC DQS Pin')
                        elif not len(line_byte.split()) == 3:
                            print ('E010: Error in reading DDR Byte SoC DQS Pin: Number of pin is not 2')
                        else:
                            thisByte.dqs_p.socPin = line_byte.split()[1]
                            thisByte.dqs_n.socPin = line_byte.split()[2]
                            thisByte.dqs_p.socModelTx, thisByte.dqs_p.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dqs_p.socPin)
                            thisByte.dqs_n.socModelTx, thisByte.dqs_n.socModelRx = self.findModel(thisInterface, thisByte.socComp, thisByte.dqs_n.socPin)
                            logging.debug (thisByte.dqs_p.socPin)
                        line_byte = next(infile)
                        if not 'DRAM' in line_byte:
                            print ('E011: Error in reading DDR Byte DRAM component')
                        else:
                            thisByte.ddrComp = line_byte.split()[-1]
                            logging.debug (thisByte.ddrComp)
                        line_byte = next(infile)
                        if not 'DRAM_Pin_DQ' in line_byte:
                            print ('E012: Error in reading DDR Byte DRAM DQ Pin')
                        elif not len(line_byte.split()) == 9:
                            print ('E013: Error in reading DDR Byte DRAM DQ Pin: Number of pin is not 8')
                        else:
                            thisByte.dq0.ddrPin = line_byte.split()[1]
                            thisByte.dq1.ddrPin = line_byte.split()[2]
                            thisByte.dq2.ddrPin = line_byte.split()[3]
                            thisByte.dq3.ddrPin = line_byte.split()[4]
                            thisByte.dq4.ddrPin = line_byte.split()[5]
                            thisByte.dq5.ddrPin = line_byte.split()[6]
                            thisByte.dq6.ddrPin = line_byte.split()[7]
                            thisByte.dq7.ddrPin = line_byte.split()[8]
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq0.ddrPin); thisByte.dq0.ddrModelTx.append(txmodel); thisByte.dq0.ddrModelRx.append(rxmodel) 
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq1.ddrPin); thisByte.dq1.ddrModelTx.append(txmodel); thisByte.dq1.ddrModelRx.append(rxmodel)
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq2.ddrPin); thisByte.dq2.ddrModelTx.append(txmodel); thisByte.dq2.ddrModelRx.append(rxmodel)
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq3.ddrPin); thisByte.dq3.ddrModelTx.append(txmodel); thisByte.dq3.ddrModelRx.append(rxmodel)
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq4.ddrPin); thisByte.dq4.ddrModelTx.append(txmodel); thisByte.dq4.ddrModelRx.append(rxmodel)
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq5.ddrPin); thisByte.dq5.ddrModelTx.append(txmodel); thisByte.dq5.ddrModelRx.append(rxmodel)
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq6.ddrPin); thisByte.dq6.ddrModelTx.append(txmodel); thisByte.dq6.ddrModelRx.append(rxmodel)
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dq7.ddrPin); thisByte.dq7.ddrModelTx.append(txmodel); thisByte.dq7.ddrModelRx.append(rxmodel)
                            logging.debug (thisByte.dq0.ddrModelRx)
                        line_byte = next(infile)
                        if not 'DRAM_Pin_DQS' in line_byte:
                            print ('E014: Error in reading DDR Byte DRAM DQS Pin')
                        elif not len(line_byte.split()) == 3:
                            print ('E015: Error in reading DDR Byte DRAM DQS Pin: Number of pin is not 2')
                        else:
                            thisByte.dqs_p.ddrPin = line_byte.split()[1]
                            thisByte.dqs_n.ddrPin = line_byte.split()[2]
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dqs_p.ddrPin); thisByte.dqs_p.ddrModelTx.append(txmodel); thisByte.dqs_p.ddrModelRx.append(rxmodel); 
                            txmodel, rxmodel = self.findModel(thisInterface, thisByte.ddrComp, thisByte.dqs_n.ddrPin); thisByte.dqs_n.ddrModelTx.append(txmodel); thisByte.dqs_n.ddrModelRx.append(rxmodel); 
                            logging.debug (thisByte.dqs_p.ddrModelRx)
                        nextline = next(infile)
                        if not 'Net_DQ' in nextline:
                            print ('E015_3: Error in reading DDR Net_DQ')
                        else:
                            nextline = next(infile)
                        if not 'Net_DQS' in nextline:
                            print ('E015_3: Error in reading DDR Net_DQS')
                        else:
                            nextline = next(infile)
                        #nextline = next(infile) # Skip the '}' line
                        nextline = next(infile)
                    logging.debug('Num of Byte: ' + str(thisInterface.numByte))

                # Parse for CTRL (SoC)
                if not 'SoC_CLK_ADR_CTRL {' in nextline:
                    print ('E016: Cannot find DDR CTRL (SoC)')
                else:
                    thisInterface.ctrl = Ctrl()
                    thisCtrl = thisInterface.ctrl
                    line_ctrl = next(infile)
                    if not 'Component' in line_ctrl:
                        print ('E017: Error in reading DDR CTRL Component')
                    else:
                        thisCtrl.socComp = line_ctrl.split()[-1]
                        logging.debug (thisCtrl.socComp)
                    line_ctrl = next(infile)
                    if not 'Pin_CLK' in line_ctrl:
                        print ('E018: Error in reading DDR CTRL Pin_CLK')
                    else:
                        thisCtrl.clk_p.socPin = line_ctrl.split()[1]
                        thisCtrl.clk_n.socPin = line_ctrl.split()[2]
                        #thisCtrl.clk_p.socModelName = self.findModel(thisInterface, thisCtrl.socComp, thisCtrl.clk_p.socPin)
                        #thisCtrl.clk_n.socModelName = self.findModel(thisInterface, thisCtrl.socComp, thisCtrl.clk_n.socPin)
                        logging.debug (thisCtrl.clk_p.socPin)
                    line_ctrl = next(infile)
                    if not 'Pin_ADR' in line_ctrl:
                        print ('E019: Error in reading DDR CTRL Pin_ADR')
                    else:
                        for i in range(len(line_ctrl.split())-1):
                            thisCtrl.addr.append(Signal('addr'+str(i)))
                            thisCtrl.addr[-1].socPin = line_ctrl.split()[i+1]
                            #thisCtrl.addr[-1].socModelName = self.findModel(thisInterface, thisCtrl.socComp, thisCtrl.addr[-1].socPin)
                        logging.debug(len(thisCtrl.addr))
                        logging.debug(thisCtrl.addr[-1].socPin)
                    line_ctrl = next(infile)
                    if not 'Pin_BA' in line_ctrl:
                        print ('E020: Error in reading DDR CTRL Pin_BA')
                    else:
                        for i in range(len(line_ctrl.split())-1):
                            thisCtrl.bank.append(Signal('addr'+str(i)))
                            thisCtrl.bank[-1].socPin = line_ctrl.split()[i+1]
                            #thisCtrl.bank[-1].socModelName = self.findModel(thisInterface, thisCtrl.socComp, thisCtrl.bank[-1].socPin)
                        logging.debug(len(thisCtrl.bank))
                        logging.debug(thisCtrl.bank[-1].socPin)
                    line_ctrl = next(infile)
                    if not 'Pin_RAS_CAS_WE' in line_ctrl:
                        print ('E021: Error in reading DDR CTRL Pin_RAS_CAS_WE')
                    else:
                        for i in range(len(line_ctrl.split())-1):
                            thisCtrl.ctrl.append(Signal('addr'+str(i)))
                            thisCtrl.ctrl[-1].socPin = line_ctrl.split()[i+1]
                            #thisCtrl.ctrl[-1].socModelName = self.findModel(thisInterface, thisCtrl.socComp, thisCtrl.ctrl[-1].socPin)
                        logging.debug(len(thisCtrl.ctrl))
                        logging.debug(thisCtrl.ctrl[-1].socPin)

                # Parse for CTRL (DRAM)
                nextline = next(infile)
                nextline = next(infile)
                if not 'DRAM_CLK_ADR_CTRL {' in nextline:
                    print ('E022: Cannot find DDR CTRL (DRAM)')
                else:
                    while 'DRAM_CLK_ADR_CTRL {' in nextline:
                        thisCtrl.numDDRComp += 1
                        line_ctrl = next(infile)
                        if not 'Component' in line_ctrl:
                            print ('E023: Error in reading DDR CTRL Component')
                        else:
                            thisCtrl.ddrComp.append(line_ctrl.split()[-1])
                            logging.debug(thisCtrl.ddrComp[-1])
                        line_ctrl = next(infile)
                        if not 'Pin_CLK' in line_ctrl:
                            print ('E024: Error in reading DDR CTRL Pin_CLK')
                        else:
                            thisCtrl.clk_p.ddrPin.append(line_ctrl.split()[1])
                            thisCtrl.clk_n.ddrPin.append(line_ctrl.split()[2])
                            #thisCtrl.clk_p.ddrModelName.append(self.findModel(thisInterface, thisCtrl.ddrComp[-1], thisCtrl.clk_p.ddrPin[-1]))
                            #thisCtrl.clk_n.ddrModelName.append(self.findModel(thisInterface, thisCtrl.ddrComp[-1], thisCtrl.clk_n.ddrPin[-1]))
                        logging.debug(thisCtrl.clk_n.ddrPin)
                        line_ctrl = next(infile)
                        if not 'Pin_ADR' in line_ctrl:
                            print ('E025: Error in reading DDR CTRL Pin_ADR')
                        else:
                            for i in range(len(line_ctrl.split())-1):
                                thisCtrl.addr[i].ddrPin.append(line_ctrl.split()[i+1])
                                #thisCtrl.addr[i].ddrModelName.append(self.findModel(thisInterface, thisCtrl.ddrComp[-1], thisCtrl.addr[i].ddrPin[-1]))
                                logging.debug(thisCtrl.addr[i].ddrPin)
                        line_ctrl = next(infile)
                        if not 'Pin_BA' in line_ctrl:
                            print ('E026: Error in reading DDR CTRL Pin_BA')
                        else:
                            for i in range(len(line_ctrl.split())-1):
                                thisCtrl.bank[i].ddrPin.append(line_ctrl.split()[i+1])
                                #thisCtrl.bank[i].ddrModelName.append(self.findModel(thisInterface, thisCtrl.ddrComp[-1], thisCtrl.bank[i].ddrPin[-1]))
                                logging.debug(thisCtrl.bank[i].ddrPin)
                        line_ctrl = next(infile)
                        if not 'Pin_RAS_CAS_WE' in line_ctrl:
                            print ('E027: Error in reading DDR CTRL Pin_RAS_CAS_WE')
                        else:
                            for i in range(len(line_ctrl.split())-1):
                                thisCtrl.ctrl[i].ddrPin.append(line_ctrl.split()[i+1])
                                #thisCtrl.ctrl[i].ddrModelName.append(self.findModel(thisInterface, thisCtrl.ddrComp[-1], thisCtrl.ctrl[i].ddrPin[-1]))
                                logging.debug(thisCtrl.ctrl[i].ddrPin)
                        nextline = next(infile)
                        nextline = next(infile)
                    logging.debug(thisCtrl.numDDRComp)

    def parseIbis (self, thisInterface):
        logging.info("Start reading IBIS file for components......")
        for i in range(len(thisInterface.comps)):
            ibisFile = self.modelPath + '/' + thisInterface.comps[i].compModelFile
            thisComp = thisInterface.comps[i]
            thisIbis = thisComp.compIbis
            if not os.path.isfile(ibisFile):
                print ('EM02: Cannot find (ibisFile) model file: %s'%(ibisFile))
            # Determine number of component in the ibis file
            IbisCompNameList = self.parseIbisCompNum(ibisFile)
            logging.debug('In IBIS file %s, the total number of component is %s.' %(thisInterface.comps[i].compModelFile, len(IbisCompNameList)))
            # Parse for Model Type
            self.parseIbisModelType(thisComp, ibisFile)
            
            # Special treatment for DIMM parts
            if thisComp.isDIMM == 1:
                print('This is a DIMM part. Do not parse IBIS.')
                continue
            
            # Special treatment for Xilinx parts
            if thisComp.compManufacture.lower() == 'xilinx':
                print('This is a Xilinx part. Do not parse IBIS.')
                continue
            
            # Determine the component to use
            IbisCompName = self.parseIbisWhichComp(IbisCompNameList, thisComp)
            # Parse for ibis model
            preline = ''
            with open(ibisFile, 'r') as f:
                found_comp = 0
                for line in f:
                    if line.startswith('|') or line.strip()=='':
                        continue
                    if line.lower().startswith('[component]') and IbisCompName.lower() in line.lower() and not 'CLP' in line:
                        found_comp = 1
                        continue
                    if found_comp == 1:
                        if line.lower().startswith('[package]'):
                            nextline = next(f)
                            while not ( nextline.startswith('[') ):
                                if 'r_pkg' in nextline.lower():
                                    #r_pkg = self.str2num(nextline.split()[1])    # ATT: This is the 'typ' case
                                    thisComp.r_pkg = nextline.split()[1]
                                if 'l_pkg' in nextline.lower():
                                    #l_pkg = self.str2num(nextline.split()[1])    # ATT: This is the 'typ' case     
                                    thisComp.l_pkg = nextline.split()[1]
                                if 'c_pkg' in nextline.lower():
                                    #c_pkg = self.str2num(nextline.split()[1])    # ATT: This is the 'typ' case
                                    thisComp.c_pkg = nextline.split()[1]
                                nextline = next(f)
                            logging.debug('D021: Parsed package parasitics: %s  %s  %s'%(thisComp.r_pkg, thisComp.l_pkg, thisComp.c_pkg))
                            if nextline.lower().startswith('[pin]'):
                                nextline = next(f)
                                while not ( nextline.startswith('[') ):
                                    thisIbis.ibis_pin2signal[nextline.split()[0]] = nextline.split()[1]
                                    thisIbis.ibis_pin2selector[nextline.split()[0]] = nextline.split()[2]
                                    if len(nextline.split()) >= 6:
                                        thisIbis.ibis_pin2rpin[nextline.split()[0]] = nextline.split()[3]
                                        thisIbis.ibis_pin2lpin[nextline.split()[0]] = nextline.split()[4]
                                        thisIbis.ibis_pin2cpin[nextline.split()[0]] = nextline.split()[5]
                                    else:
                                        thisIbis.ibis_pin2rpin[nextline.split()[0]] = ''
                                        thisIbis.ibis_pin2lpin[nextline.split()[0]] = ''
                                        thisIbis.ibis_pin2cpin[nextline.split()[0]] = ''
                                    nextline = next(f)
                                    while nextline.startswith('|') or nextline.strip()=='':
                                        nextline = next(f)
                                found_comp = 0
                    if line.lower().startswith('[model selector]'):
                        selector = line.split()[-1]
                        nextline = next(f)
                        while not ( nextline.startswith('[') ):
                            if nextline.startswith('|') or nextline.strip()=='':
                                nextline = next(f)
                                continue
                            #thisIbis.ibis_selector2model[selector].append(nextline.split()[0])
                            thisIbis.ibis_selector2model[selector].append(nextline)
                            nextline = next(f)
                        preline = nextline
                    elif preline.lower().startswith('[model selector]'):
                        selector = preline.split()[-1]
                        #logging.debug('Preline:  ' + selector)
                        nextline = line
                        while not ( nextline.startswith('[') ):
                            if nextline.startswith('|') or nextline.strip()=='':
                                nextline = next(f)
                                continue
                            #thisIbis.ibis_selector2model[selector].append(nextline.split()[0])
                            thisIbis.ibis_selector2model[selector].append(nextline)
                            nextline = next(f)
                        preline = nextline
                    if preline.lower().startswith('[model]'):
                        #logging.debug('break line:  ' + preline)
                        break    
                logging.debug('D022: All Model Selectors: %s' % (thisIbis.ibis_selector2model.keys()))
                #print("############# pin to model selector ################")
                #print(thisIbis.ibis_pin2selector)
            
    def parseIbisModelType (self, thisComp, ibisFile):
        # Parse for Model Type
        with open(ibisFile, 'r') as f:
            for line in f:
                if line.lower().startswith('[model]'):
                    modelname = line.split()[-1]
                    nextline = next(f)
                    while not nextline.startswith('['):
                        if 'model_type' in nextline.lower():
                            thisComp.compIbis.ibis_model2type[modelname] = nextline.split()[-1]
                        if 'enable' in nextline.lower():
                                if 'low' in nextline.lower():
                                    thisComp.compIbis.ibis_model2enable[modelname] = '0'
                                else:
                                    thisComp.compIbis.ibis_model2enable[modelname] = '1'
                        nextline = next(f)
                    if not modelname in thisComp.compIbis.ibis_model2enable.keys():
                        thisComp.compIbis.ibis_model2enable[modelname] = '1'
        for key in thisComp.compIbis.ibis_model2type:   # output the model type for all models.
            #logging.debug('D023 - Model: %s. Type: %s.' % (key, thisComp.compIbis.ibis_model2type[key]))
            pass
                    

    def findModel(self, thisInterface, compName, pinName):
        found_comp = 0
        for c in thisInterface.comps:
            if compName == c.compID:
                thisComp = c
                found_comp = 1
                break
        if found_comp == 0:
            print ('EM01: Cannot find component: %s'%(compName))
            return '' 
        
        # For Xilinx part
        if thisComp.compManufacture.lower() == 'xilinx':
            if self.interfaces[0].ddrType.lower() == 'ddr2':
                return ['SSTL18_II_F_HR', 'SSTL18_II_F_HR']
            if self.interfaces[0].ddrType.lower() == 'ddr3':
                return ['SSTL15_F_HR', 'SSTL15_F_HR']
        
        # For DIMM part
        # DQ_DRV_34           DQ DRV Ron 34ohm ( ODT OFF )
        # DQ_DRV_40           DQ DRV Ron 40ohm ( ODT OFF )
        # DIN_ODT_OFF         DQ ODT OFF ( Driver/ODT OFF )
        # DIN_ODT_120         DQ ODT 120ohm ( Driver OFF )
        # DIN_ODT_60          DQ ODT 60ohm  ( Driver OFF )
        # DIN_ODT_40          DQ ODT 40ohm  ( Driver OFF )
        # DIN_ODT_30          DQ ODT 30ohm  ( Driver OFF )
        # DIN_ODT_20          DQ ODT 20ohm  ( Driver OFF )        
        if thisComp.isDIMM == 1:
            if thisComp.compManufacture.lower() == 'hynix':
                return ['DQ_DRV_34', 'DIN_ODT_40']
            
        # For non-Xilinx, non-DIMM part
        if not (pinName in thisComp.compIbis.ibis_pin2selector.keys() ):
            print ('EM02: Cannot find pin %s in IBIS model.' %(pinName))
            return ''
        selectorName = thisComp.compIbis.ibis_pin2selector[pinName]
        if not (selectorName in thisComp.compIbis.ibis_selector2model.keys()):
            print ('EM03: Cannot find model selector %s in IBIS model for pin %s.' %(selectorName, pinName))
            return ''
        modelNameList = thisComp.compIbis.ibis_selector2model[selectorName]
        #logging.debug('D030: IBIS model list for pin %s is %s' %(pinName, modelNameList))
        logging.debug('D031: IBIS model selector for pin %s is %s' %(pinName, selectorName))
        
        # Determine model for Micron part
        if thisComp.compManufacture == 'Micron' and self.interfaces[0].ddrType.lower() == 'ddr2':
            # Parsor for Micron DDR2 IBIS Model            
            # simulate with the DQ_FULL or DQ_HALF model for ALL Output simulations.  Use the ODT models ONLY for Input simulations.
            DS = '_FULL'    # _FULL, _HALF
            tx_model_candidate = []
            tx_model = ''
            for thisModel in modelNameList:
                if thisInterface.dataRate in thisModel.split()[0] and DS in thisModel.split()[0] and 'ODT' not in thisModel.split()[0]:
                    tx_model_candidate.append(thisModel.split()[0])
            if len(tx_model_candidate)==0:
                print('W01: Mircon Part: Cannot find coresponding datarate (%s) for pin %s in the IBIS model. Using generic model.'%(thisInterface.dataRate, pinName))
                tx_model = modelNameList[0].split()[0]  # use the first model in the list
            else:
                tx_model = tx_model_candidate[0]
            logging.debug('D032: Tx model for pin %s is %s. Model Type is %s.'%(pinName, tx_model, thisComp.compIbis.ibis_model2type[tx_model]))
            
            # Rx model: Use DQ_34_ODT*_* for ODT termination, otherwise use DQ_34_*, DQ_40_*
            ODT = '_ODT50'  # _ODT50, _ODT75, _ODT150
            rx_model_candidate = []
            rx_model = ''
            for thisModel in modelNameList:
                if thisInterface.dataRate in thisModel.split()[0] and DS in thisModel.split()[0] and ODT in thisModel.split()[0]:
                    rx_model_candidate.append(thisModel.split()[0])
            if len(rx_model_candidate)==0:
                print('W02: Mircon Part: Cannot find coresponding datarate (%s) for pin %s. Using generic model.'%(thisInterface.dataRate, pinName))
                rx_model = modelNameList[0].split()[0]  # use the first model in the list
            else:
                rx_model = rx_model_candidate[0]
            logging.debug('D033: Rx model for pin %s is %s. Model Type is %s.'%(pinName, rx_model, thisComp.compIbis.ibis_model2type[rx_model]))
            return [tx_model, rx_model]
            
        if thisComp.compManufacture == 'Micron' and self.interfaces[0].ddrType.lower() == 'ddr3':
            # Parsor for Micron DDR3 IBIS Model
            # Tx model: only use DQ_34_*, DQ_40_*
            DS = '_40'
            tx_model_candidate = []
            tx_model = ''
            for thisModel in modelNameList:
                # modelNameList: 'DQ_34_1066 34 Ohm Data I/O with no ODT, 800/1066Mbps\n', ...
                if thisInterface.dataRate in thisModel.split()[0] and DS in thisModel.split()[0] and 'ODT' not in thisModel.split()[0]:
                    tx_model_candidate.append(thisModel.split()[0])
            if len(tx_model_candidate)==0:
                print('W01: Mircon Part: Cannot find coresponding datarate (%s) for pin %s in the IBIS model. Using generic model.'%(thisInterface.dataRate, pinName))
                tx_model = modelNameList[0].split()[0]  # use the first model in the list
            else:
                tx_model = tx_model_candidate[0]
            logging.debug('D032: Tx model for pin %s is %s. Model Type is %s.'%(pinName, tx_model, thisComp.compIbis.ibis_model2type[tx_model]))
            
            # Rx model: Use DQ_34_ODT*_* for ODT termination, otherwise use DQ_34_*, DQ_40_*
            ODT = '_ODT40'  # choose from: '', 'ODT40', 'ODT60', 'ODT120'
            rx_model_candidate = []
            rx_model = ''
            for thisModel in modelNameList:
                if thisInterface.dataRate in thisModel.split()[0] and DS in thisModel.split()[0] and ODT in thisModel.split()[0]:
                    rx_model_candidate.append(thisModel.split()[0])
            if len(rx_model_candidate)==0:
                print('W02: Mircon Part: Cannot find coresponding datarate (%s) for pin %s. Using generic model.'%(thisInterface.dataRate, pinName))
                rx_model = modelNameList[0].split()[0]  # use the first model in the list
            else:
                rx_model = rx_model_candidate[0]
            logging.debug('D033: Rx model for pin %s is %s. Model Type is %s.'%(pinName, rx_model, thisComp.compIbis.ibis_model2type[rx_model]))
            return [tx_model, rx_model]
        
        # Determine model for TI part
        if thisComp.compManufacture == 'TI':
            # Parsor for TI Micro controller IBIS Model
            # Tx model:
            # Model_100 3-STATE,1.5V,SLOWEST, 7MA,IND,10%
            # output model
            driverType = '3-state'
            DS = '8ma'
            swing = '1.5v'
            edgeRate = 'slow'
            tx_model_candidate = []
            tx_model = ''
            for thisModel in modelNameList:
                if driverType in thisModel.lower() and DS in thisModel.lower() and edgeRate in thisModel.lower().split(',') and swing in thisModel.lower():
                    tx_model_candidate.append(thisModel.split()[0])
            if len(tx_model_candidate)==0:
                print('W03: TI Part: Cannot find coresponding model for pin %s in the IBIS file. Using generic model.'%(pinName))
            else:
                tx_model = tx_model_candidate[0]
            logging.debug('D034: IBIS Tx model for pin %s is %s. Model Type is %s.'%(pinName, tx_model, thisComp.compIbis.ibis_model2type[tx_model]))
            # Rx model:
            driverType = 'input'
            DS = '8ma'
            swing = '1.5v'
            term = 'halfterm'   # 'fullterm', 'halfterm', 'pull-up,', 'pull-down', 'pull-up/down off'
            rx_model_candidate = []
            rx_model = ''
            for thisModel in modelNameList:
                if driverType in thisModel.lower() and DS in thisModel.lower() and term in thisModel.lower().split(',') and swing in thisModel.lower():
                    rx_model_candidate.append(thisModel.split()[0])
            if len(rx_model_candidate)==0:
                print('W04: TI Part: Cannot find coresponding model for pin %s in the IBIS file. Using generic model.'%(pinName))
            else:
                rx_model = rx_model_candidate[0]
            logging.debug('D035: IBIS Rx model for pin %s is %s. Model Type is %s.'%(pinName, rx_model, thisComp.compIbis.ibis_model2type[rx_model]))        
            return [tx_model, rx_model]

        # Determine model for Telechips part
        if thisComp.compManufacture.lower() == 'telechips':
            #pbsstl_100 1X Driver
            #pbsstl_101 2X Driver
            #pbsstl_110 3X Driver
            #pbsstl_111 4X Driver
            #ODT120        ODT120_ZQ240
            #ODT60         ODT60_ZQ240
            #ODT40         ODT40_ZQ240
            #ODT30         ODT30_ZQ240
            # Tx model
            DS = '_111'
            tx_model_candidate = []
            tx_model = ''
            for thisModel in modelNameList:
                if DS in thisModel.split()[0] and 'ODT' not in thisModel.split()[0]:
                    tx_model_candidate.append(thisModel.split()[0])
            if len(tx_model_candidate) == 0:
                print('W05 - Telechips Part: Cannot find coresponding datarate (%s) for pin %s in the IBIS model. Using generic model.'%(thisInterface.dataRate, pinName))
                tx_model = modelNameList[0].split()[0]  # use the first model in the list
            else:
                tx_model = tx_model_candidate[0]
            logging.debug('D036: Tx model for pin %s is %s. Model Type is %s.'%(pinName, tx_model, thisComp.compIbis.ibis_model2type[tx_model]))
            # Rx model
            ODT = 'ODT40'  # choose from: '', 'ODT30', 'ODT40', 'ODT60', 'ODT120'
            rx_model_candidate = []
            rx_model = ''
            for thisModel in modelNameList:
                if ODT in thisModel.split()[0]:
                    rx_model_candidate.append(thisModel.split()[0])
            if len(rx_model_candidate)==0:
                print('W06: Telechips Part: Cannot find coresponding datarate (%s) for pin %s. Using generic model.'%(thisInterface.dataRate, pinName))
                rx_model = modelNameList[0].split()[0]  # use the first model in the list
            else:
                rx_model = rx_model_candidate[0]
            print ('rx_model: ' + rx_model)
            logging.debug('D037: Rx model for pin %s is %s. Model Type is %s.'%(pinName, rx_model, thisComp.compIbis.ibis_model2type[rx_model]))
            return [tx_model, rx_model]
        
        return ['', '']

    def generateByteDeck(self, deckType):
        if len(self.interfaces) > 1:
            print('EG01: More than one interface in current configure file. Current not supported.')
            raise SystemExit
        thisInterface = self.interfaces[0]
        for i in range(len(self.interfaces[0].byte)):
            thisByte = self.interfaces[0].byte[i]
            deckfile = self.modelPath + '/../decks/' + 'byte' + thisByte.byteID + '_' + deckType + '.sp'
            deck = []   # the content of deck
            # header
            deck.append("* Deck for Byte%s %s\n"%(thisByte.byteID , deckType.upper()))
            deck.append(".options post probe")
            deck.append("* .options method=gear dcon=1 converge=1")
            deck.append(".tran 10p 100n")
            deck.append("")
            # data and clock pattern
            param_ground = '0.000'
            param_vcc = '1.500'
            param_datarate = thisInterface.dataRate+'e6'
            param_freq = str(float(param_datarate)/2)
            param_delay = '1e-9'
            param_dataslew = '50e-12'
            param_dataclkslew = '50e-12'
            param_pulsewidth = str(1/float(param_datarate)-float(param_dataslew))
            param_per = str(2/float(param_datarate))
            deck.append("*********************************")
            deck.append("***** DATA AND CLK PATTERN ******")
            deck.append("*********************************")
            deck.append(".param ground = %s" %(param_ground))
            deck.append(".param vcc = %s" %(param_vcc))
            deck.append(".param delay = %s" %(param_delay))
            deck.append(".param dataslew = %s" %(param_dataslew))
            deck.append(".param dataclkslew = %s" %(param_dataclkslew))
            deck.append(".param datarate = %se6" % (thisInterface.dataRate))
            deck.append(".param freq = 'datarate/2'")
            deck.append(".param pulsewidth = '1/datarate - dataslew'")
            deck.append(".param clkpw = '1/datarate - dataclkslew'")
            deck.append(".param per = '2*(1/datarate)'")
            deck.append(".param clkper = '2*(1/datarate)'")
            deck.append(".param delayclk = 'delay-(clkper/4)'")
            deck.append("")
            # DQ, DQS excitations
            deck.append("* DQ, DQS pattern")
            deck.append("* V_dq0 dq0_in 0 LFSR ground vcc delay dataslew dataslew datarate 80 [7,6]  rout=0")
            for k in range(8):
                if k == 4:
                    deck.append("V_dq%s dq%s_in 0 LFSR %s %s %s %s %s %s 17 [7,6]  rout=0" %(str(k), str(k), param_ground, param_vcc, param_delay, param_dataslew, param_dataslew, param_datarate))
                else:
                    deck.append("V_dq%s dq%s_in 0 LFSR %s %s %s %s %s %s 80 [7,6]  rout=0" %(str(k), str(k), param_ground, param_vcc, param_delay, param_dataslew, param_dataslew, param_datarate))
            deck.append("* V_dqs_p dqs_p_in 0 PULSE ground vcc delay dataslew dataslew pulsewidth per")
            deck.append("V_dqs_p dqs_p_in 0 PULSE %s %s %s %s %s %s %s" %(param_ground, param_vcc, param_delay, param_dataslew, param_dataslew, param_pulsewidth, param_per))
            deck.append("V_dqs_n dqs_n_in 0 PULSE %s %s %s %s %s %s %s"%(param_vcc, param_ground, param_delay, param_dataslew, param_dataslew, param_pulsewidth, param_per))
            deck.append("")
            
            if deckType == 'rd':
                # DDR model: Tx 
                thisComp = self.getComp(thisInterface, thisByte.ddrComp)
                deck.append("*********************************")
                deck.append("******* DDR Model (Tx) **********")
                deck.append("*********************************")
                # DQ subckt model, includes pkg model
                deck.append("******* DQ subckt *******")
                dq_model_type = thisComp.compIbis.ibis_model2type[thisByte.dq0.ddrModelTx[0]]
                deck.append(".subckt tx_model_dq nd_pkg_out nd_in rpin=100m lpin=1nH cpin=0.2pF")
                if (dq_model_type.lower() == 'i/o'):
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en nd_dig_out")
                elif (dq_model_type.lower() == '3-state'):    
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en")
                else:
                    print('E029: IBIS model type is not supported: %s' %(dq_model_type))
                    raise SystemExit
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))      # absolute path
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dq0.ddrModelTx[0]))   # ATTN
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") # 1-Input; 2-Output; 3-I/O; 4-Three state
                deck.append("v_en nd_en 0 %s" % (thisComp.compIbis.ibis_model2enable[thisByte.dq0.ddrModelTx[0]]))
                deck.append("x_pin nd_die_out nd_pin_out pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                deck.append("x_ddr_pkg nd_pin_out nd_pkg_out ddr_pkg")
                deck.append(".ends")
                deck.append("")
                if thisByte.dq0.ddrPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.ddrPin] == '':
                    deck.append("xtx_dq0 dq0_ddr_bga dq0_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq0.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq0.ddrPin]))
                    deck.append("xtx_dq1 dq1_ddr_bga dq1_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq1.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq1.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq1.ddrPin]))
                    deck.append("xtx_dq2 dq2_ddr_bga dq2_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq2.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq2.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq2.ddrPin]))
                    deck.append("xtx_dq3 dq3_ddr_bga dq3_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq3.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq3.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq3.ddrPin]))
                    deck.append("xtx_dq4 dq4_ddr_bga dq4_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq4.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq4.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq4.ddrPin]))
                    deck.append("xtx_dq5 dq5_ddr_bga dq5_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq5.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq5.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq5.ddrPin]))
                    deck.append("xtx_dq6 dq6_ddr_bga dq6_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq6.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq6.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq6.ddrPin]))
                    deck.append("xtx_dq7 dq7_ddr_bga dq7_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq7.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq7.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq7.ddrPin]))
                else:
                    deck.append("xtx_dq0 dq0_ddr_bga dq0_in tx_model_dq")
                    deck.append("xtx_dq1 dq1_ddr_bga dq1_in tx_model_dq")
                    deck.append("xtx_dq2 dq2_ddr_bga dq2_in tx_model_dq")
                    deck.append("xtx_dq3 dq3_ddr_bga dq3_in tx_model_dq")
                    deck.append("xtx_dq4 dq4_ddr_bga dq4_in tx_model_dq")
                    deck.append("xtx_dq5 dq5_ddr_bga dq5_in tx_model_dq")
                    deck.append("xtx_dq6 dq6_ddr_bga dq6_in tx_model_dq")
                    deck.append("xtx_dq7 dq7_ddr_bga dq7_in tx_model_dq")
                deck.append("\n******* DQS subckt *******")
                deck.append(".subckt tx_model_dqs nd_pkg_out nd_in rpin=100m lpin=1nH cpin=0.2pF")
                dqs_model_type = thisComp.compIbis.ibis_model2type[thisByte.dqs_p.ddrModelTx[0]]
                if (dqs_model_type.lower() == 'i/o'):
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en nd_dig_out")
                elif (dqs_model_type.lower() == '3-state'):    
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en")
                else:
                    print('E030: IBIS model type is not supported: %s' %(dqs_model_type))
                    raise SystemExit                
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dqs_p.ddrModelTx[0])) # ATTN: Assuming DQS_P and DQS_N using same model (mostly true).
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") 
                deck.append("v_en nd_en 0 %s" % (thisComp.compIbis.ibis_model2enable[thisByte.dqs_p.ddrModelTx[0]]))  # enabled
                deck.append("x_pin nd_die_out nd_pin_out pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                deck.append("x_ddr_pkg nd_pin_out nd_pkg_out ddr_pkg")
                deck.append(".ends")
                deck.append("")
                if thisByte.dqs_p.ddrPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.ddrPin] == '':
                    deck.append("xtx_dqsp dqs_p_ddr_bga dqs_p_in tx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_p.ddrPin],thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_p.ddrPin]))
                    deck.append("xtx_dqsn dqs_n_ddr_bga dqs_n_in tx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_n.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_n.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_n.ddrPin]))
                else:
                    deck.append("xtx_dqsp dqs_p_ddr_bga dqs_p_in tx_model_dqs")
                    deck.append("xtx_dqsn dqs_n_ddr_bga dqs_n_in tx_model_dqs")
                deck.append("")
                
                # SoC model: Rx
                thisComp = self.getComp(thisInterface, thisByte.socComp)
                deck.append("*********************************")
                deck.append("******* SoC Model (Rx) **********")
                deck.append("*********************************")
                deck.append("******* DQ Rx subckt *******")
                deck.append(".subckt rx_model_dq rx_pkg_in rx_dig_out rpin=100m lpin=1nH cpin=0.2pF")
                #logging.debug('The DQ Rx model for this byte is: %s, pin %s' % (thisByte.dq0.socModelRx, thisByte.dq0.socPin))
                dq_model_type = thisComp.compIbis.ibis_model2type[thisByte.dq0.socModelRx]
                if (dq_model_type.lower() == 'i/o'):
                    deck.append("v_en nd_en 0 %s" % (str(1-int(thisComp.compIbis.ibis_model2enable[thisByte.dq0.socModelRx]))))  # disabled                 
                    deck.append("B_dq nd_pu nd_pd rx_pad nd_in nd_en rx_dig_out")
                elif (dq_model_type.lower() == 'input'):    
                    deck.append("B_dq nd_pc nd_gc rx_pad rx_dig_out")    
                else:
                    print('E031: IBIS model type is not supported: %s' %(dq_model_type))
                    raise SystemExit
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dq0.socModelRx))
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") # 1-Input; 2-Output; 3-I/O; 4-Three state
                deck.append("x_pin rx_pad nd_pin_in pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                #deck.append("x_pin rx_pad nd_pin_in pin_rlc")
                deck.append("x_soc_pkg rx_pad rx_pkg_in soc_pkg")
                deck.append(".ends")
                deck.append("")
                # Generic Rx model
                #deck.append(".subckt rx_model rx_pkg_in")
                #deck.append("x_rx rx_pad rx_pkg_in soc_pkg")
                #deck.append("*R_pu rx_pad vcc R_ODT")
                #deck.append("*R_pd rx_pad 0 R_ODT")
                #deck.append("C_pin rx_pad 0 1.8pF")
                #deck.append(".ends")
                #deck.append("")
                if thisByte.dq0.socPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.socPin] == '':
                    deck.append("xrx_dq0 dq0_soc_bga dq0_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq0.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq0.socPin]))
                    deck.append("xrx_dq1 dq1_soc_bga dq1_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq1.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq1.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq1.socPin]))
                    deck.append("xrx_dq2 dq2_soc_bga dq2_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq2.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq2.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq2.socPin]))
                    deck.append("xrx_dq3 dq3_soc_bga dq3_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq3.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq3.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq3.socPin]))
                    deck.append("xrx_dq4 dq4_soc_bga dq4_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq4.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq4.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq4.socPin]))
                    deck.append("xrx_dq5 dq5_soc_bga dq5_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq5.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq5.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq5.socPin]))
                    deck.append("xrx_dq6 dq6_soc_bga dq6_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq6.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq6.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq6.socPin]))
                    deck.append("xrx_dq7 dq7_soc_bga dq7_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq7.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq7.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq7.socPin]))
                else:
                    deck.append("xrx_dq0 dq0_soc_bga dq0_dig_out rx_model_dq")
                    deck.append("xrx_dq1 dq1_soc_bga dq1_dig_out rx_model_dq")
                    deck.append("xrx_dq2 dq2_soc_bga dq2_dig_out rx_model_dq")
                    deck.append("xrx_dq3 dq3_soc_bga dq3_dig_out rx_model_dq")
                    deck.append("xrx_dq4 dq4_soc_bga dq4_dig_out rx_model_dq")
                    deck.append("xrx_dq5 dq5_soc_bga dq5_dig_out rx_model_dq")
                    deck.append("xrx_dq6 dq6_soc_bga dq6_dig_out rx_model_dq")
                    deck.append("xrx_dq7 dq7_soc_bga dq7_dig_out rx_model_dq")
                    
                deck.append("\n******* DQS Rx subckt *******")
                deck.append(".subckt rx_model_dqs rx_pkg_in rx_dig_out rpin=100m lpin=1nH cpin=0.2pF")
                dqs_model_type = thisComp.compIbis.ibis_model2type[thisByte.dqs_p.socModelRx]
                if (dqs_model_type.lower() == 'i/o'):
                    deck.append("v_en nd_en 0 %s" % (str(1-int(thisComp.compIbis.ibis_model2enable[thisByte.dqs_p.socModelRx]))))                    
                    deck.append("B_dq nd_pu nd_pd rx_pad nd_in nd_en rx_dig_out")
                elif (dqs_model_type.lower() == 'input'):    
                    deck.append("B_dq nd_pc nd_gc rx_pad rx_dig_out")    
                else:
                    print('E031: IBIS model type is not supported: %s' %(dqs_model_type))
                    raise SystemExit
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dqs_p.socModelRx))
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") # 1-Input; 2-Output; 3-I/O; 4-Three state
                deck.append("x_pin rx_pad nd_pin_in pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                #deck.append("x_pin rx_pad nd_pin_in pin_rlc")
                deck.append("x_soc_pkg rx_pad rx_pkg_in soc_pkg")
                deck.append(".ends")
                deck.append("")
                if thisByte.dqs_p.socPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.socPin] == '':
                    deck.append("xrx_dqsp dqs_p_soc_bga dqs_p_dig_out rx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_p.socPin],thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_p.socPin]))
                    deck.append("xrx_dqsn dqs_n_soc_bga dqs_n_dig_out rx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_n.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_n.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_n.socPin]))
                else:
                    deck.append("xrx_dqsp dqs_p_soc_bga dqs_p_dig_out rx_model_dqs")
                    deck.append("xrx_dqsn dqs_n_soc_bga dqs_n_dig_out rx_model_dqs")
                deck.append("")
                
            
            if  deckType == 'wt':
                # SoC model: Tx 
                thisComp = self.getComp(thisInterface, thisByte.socComp)
                deck.append("*********************************")
                deck.append("******* SoC Model (Tx) **********")
                deck.append("*********************************")
                # DQ subckt model, includes pkg model
                deck.append("* DQ subckt")
                dq_model_type = thisComp.compIbis.ibis_model2type[thisByte.dq0.socModelTx]
                deck.append(".subckt tx_model_dq nd_pkg_out nd_in rpin=100m lpin=1nH cpin=0.2pF")
                if (dq_model_type.lower() == 'i/o'):
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en nd_dig_out")
                elif (dq_model_type.lower() == '3-state'):    
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en")
                else:
                    print('E029: IBIS model type is not supported: %s' %(dq_model_type))
                    raise SystemExit
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))      # absolute path
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dq0.socModelTx))   # ATTN
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") # 1-Input; 2-Output; 3-I/O; 4-Three state
                deck.append("v_en nd_en 0 %s" % (thisComp.compIbis.ibis_model2enable[thisByte.dq0.socModelTx]))    # enabled
                deck.append("x_pin nd_die_out nd_pin_out pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                deck.append("x_soc_pkg nd_pin_out nd_pkg_out soc_pkg")
                deck.append(".ends")
                deck.append("")
                if thisByte.dq0.socPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.socPin] == '':
                    deck.append("xtx_dq0 dq0_soc_bga dq0_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq0.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq0.socPin]))
                    deck.append("xtx_dq1 dq1_soc_bga dq1_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq1.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq1.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq1.socPin]))
                    deck.append("xtx_dq2 dq2_soc_bga dq2_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq2.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq2.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq2.socPin]))
                    deck.append("xtx_dq3 dq3_soc_bga dq3_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq3.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq3.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq3.socPin]))
                    deck.append("xtx_dq4 dq4_soc_bga dq4_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq4.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq4.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq4.socPin]))
                    deck.append("xtx_dq5 dq5_soc_bga dq5_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq5.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq5.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq5.socPin]))
                    deck.append("xtx_dq6 dq6_soc_bga dq6_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq6.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq6.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq6.socPin]))
                    deck.append("xtx_dq7 dq7_soc_bga dq7_in tx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq7.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq7.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq7.socPin]))
                else:
                    deck.append("xtx_dq0 dq0_soc_bga dq0_in tx_model_dq")
                    deck.append("xtx_dq1 dq1_soc_bga dq1_in tx_model_dq")
                    deck.append("xtx_dq2 dq2_soc_bga dq2_in tx_model_dq")
                    deck.append("xtx_dq3 dq3_soc_bga dq3_in tx_model_dq")
                    deck.append("xtx_dq4 dq4_soc_bga dq4_in tx_model_dq")
                    deck.append("xtx_dq5 dq5_soc_bga dq5_in tx_model_dq")
                    deck.append("xtx_dq6 dq6_soc_bga dq6_in tx_model_dq")
                    deck.append("xtx_dq7 dq7_soc_bga dq7_in tx_model_dq")                                  
                deck.append("\n* DQS subckt")
                deck.append(".subckt tx_model_dqs nd_pkg_out nd_in rpin=100m lpin=1nH cpin=0.2pF")
                dqs_model_type = thisComp.compIbis.ibis_model2type[thisByte.dqs_p.socModelTx]
                if (dqs_model_type.lower() == 'i/o'):
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en nd_dig_out")
                elif (dqs_model_type.lower() == '3-state'):    
                    deck.append("B_dq nd_pu nd_pd nd_die_out nd_in nd_en")
                else:
                    print('E030: IBIS model type is not supported: %s' %(dqs_model_type))
                    raise SystemExit                
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dqs_p.socModelTx)) # ATTN: Assuming DQS_P and DQS_N using same model (mostly true).
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") 
                deck.append("v_en nd_en 0 %s" % (thisComp.compIbis.ibis_model2enable[thisByte.dqs_p.socModelTx]))
                deck.append("x_pin nd_die_out nd_pin_out pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                deck.append("x_soc_pkg nd_pin_out nd_pkg_out soc_pkg")
                deck.append(".ends")
                deck.append("")
                if thisByte.dqs_p.socPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.socPin] == '':
                    deck.append("xtx_dqsp dqs_p_soc_bga dqs_p_in tx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_p.socPin],thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_p.socPin]))
                    deck.append("xtx_dqsn dqs_n_soc_bga dqs_n_in tx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_n.socPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_n.socPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_n.socPin]))
                else:
                    deck.append("xtx_dqsp dqs_p_soc_bga dqs_p_in tx_model_dqs")
                    deck.append("xtx_dqsn dqs_n_soc_bga dqs_n_in tx_model_dqs")                 
                deck.append("")
                
                # DDR model: Rx
                thisComp = self.getComp(thisInterface, thisByte.ddrComp)
                deck.append("*********************************")
                deck.append("******* DDR Model (Rx) **********")
                deck.append("*********************************")
                deck.append("* DQ Rx subckt")
                deck.append(".subckt rx_model_dq rx_pkg_in rx_dig_out rpin=100m lpin=1nH cpin=0.2pF")
                dq_model_type = thisComp.compIbis.ibis_model2type[thisByte.dq0.ddrModelRx[0]]
                if (dq_model_type.lower() == 'i/o'):
                    deck.append("v_en nd_en 0 %s" % (str(1-int(thisComp.compIbis.ibis_model2enable[thisByte.dq0.ddrModelRx[0]]))))                    
                    deck.append("B_dq nd_pu nd_pd rx_pad nd_in nd_en rx_dig_out")
                elif (dq_model_type.lower() == 'input'):    
                    deck.append("B_dq nd_pc nd_gc rx_pad rx_dig_out")    
                else:
                    print('E031: IBIS model type is not supported: %s' %(dq_model_type))
                    raise SystemExit
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dq0.ddrModelRx[0]))
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") # 1-Input; 2-Output; 3-I/O; 4-Three state
                deck.append("x_pin rx_pad nd_pin_in pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                #deck.append("x_pin rx_pad nd_pin_in pin_rlc")
                deck.append("x_ddr_pkg rx_pad rx_pkg_in ddr_pkg")
                deck.append(".ends")
                deck.append("")
                # Generic Rx model
                #deck.append(".subckt rx_model rx_pkg_in")
                #deck.append("x_rx rx_pad rx_pkg_in ddr_pkg")
                #deck.append("*R_pu rx_pad vcc R_ODT")
                #deck.append("*R_pd rx_pad 0 R_ODT")
                #deck.append("C_pin rx_pad 0 1.8pF")
                #deck.append(".ends")
                #deck.append("")
                if thisByte.dq0.ddrPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.ddrPin] == '':
                    deck.append("xrx_dq0 dq0_ddr_bga dq0_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq0.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq0.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq0.ddrPin]))
                    deck.append("xrx_dq1 dq1_ddr_bga dq1_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq1.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq1.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq1.ddrPin]))
                    deck.append("xrx_dq2 dq2_ddr_bga dq2_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq2.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq2.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq2.ddrPin]))
                    deck.append("xrx_dq3 dq3_ddr_bga dq3_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq3.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq3.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq3.ddrPin]))
                    deck.append("xrx_dq4 dq4_ddr_bga dq4_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq4.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq4.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq4.ddrPin]))
                    deck.append("xrx_dq5 dq5_ddr_bga dq5_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq5.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq5.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq5.ddrPin]))
                    deck.append("xrx_dq6 dq6_ddr_bga dq6_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq6.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq6.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq6.ddrPin]))
                    deck.append("xrx_dq7 dq7_ddr_bga dq7_dig_out rx_model_dq rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dq7.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dq7.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dq7.ddrPin]))
                else:
                    deck.append("xrx_dq0 dq0_ddr_bga dq0_dig_out rx_model_dq")
                    deck.append("xrx_dq1 dq1_ddr_bga dq1_dig_out rx_model_dq")
                    deck.append("xrx_dq2 dq2_ddr_bga dq2_dig_out rx_model_dq")
                    deck.append("xrx_dq3 dq3_ddr_bga dq3_dig_out rx_model_dq")
                    deck.append("xrx_dq4 dq4_ddr_bga dq4_dig_out rx_model_dq")
                    deck.append("xrx_dq5 dq5_ddr_bga dq5_dig_out rx_model_dq")
                    deck.append("xrx_dq6 dq6_ddr_bga dq6_dig_out rx_model_dq")
                    deck.append("xrx_dq7 dq7_ddr_bga dq7_dig_out rx_model_dq")                                  
                deck.append("\n* DQS Rx subckt")
                deck.append(".subckt rx_model_dqs rx_pkg_in rx_dig_out rpin=100m lpin=1nH cpin=0.2pF")
                dqs_model_type = thisComp.compIbis.ibis_model2type[thisByte.dqs_p.ddrModelRx[0]]
                if (dqs_model_type.lower() == 'i/o'):
                    deck.append("v_en nd_en 0 %s" % ((str(1-int(thisComp.compIbis.ibis_model2enable[thisByte.dqs_p.ddrModelRx[0]])))))                    
                    deck.append("B_dq nd_pu nd_pd rx_pad nd_in nd_en rx_dig_out")
                elif (dqs_model_type.lower() == 'input'):    
                    deck.append("B_dq nd_pc nd_gc rx_pad rx_dig_out")    
                else:
                    print('E031: IBIS model type is not supported: %s' %(dqs_model_type))
                    raise SystemExit
                deck.append('+ file = "%s"' % (self.modelPath + "/" + thisComp.compModelFile))
                #deck.append("+ file = '%s'" % ('../models/'  + thisComp.compModelFile))            # relative path
                deck.append('+ model = "%s"' %(thisByte.dqs_p.ddrModelRx[0]))
                deck.append("+ typ = typ")
                #deck.append("+ buffer = 3") # 1-Input; 2-Output; 3-I/O; 4-Three state
                deck.append("x_pin rx_pad nd_pin_in pin_rlc rpin='rpin' lpin='lpin' cpin='cpin'")
                #deck.append("x_pin rx_pad nd_pin_in pin_rlc")
                deck.append("x_ddr_pkg rx_pad rx_pkg_in ddr_pkg")
                deck.append(".ends")
                deck.append("")
                if thisByte.dqs_p.ddrPin in thisComp.compIbis.ibis_pin2rpin.keys() and not thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.ddrPin] == '':
                    deck.append("xrx_dqsp dqs_p_ddr_bga dqs_p_dig_out rx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_p.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_p.ddrPin],thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_p.ddrPin]))
                    deck.append("xrx_dqsn dqs_n_ddr_bga dqs_n_dig_out rx_model_dqs rpin=%s lpin=%s cpin=%s" %(thisComp.compIbis.ibis_pin2rpin[thisByte.dqs_n.ddrPin], thisComp.compIbis.ibis_pin2lpin[thisByte.dqs_n.ddrPin], thisComp.compIbis.ibis_pin2cpin[thisByte.dqs_n.ddrPin]))
                else:
                    deck.append("xrx_dqsp dqs_p_ddr_bga dqs_p_dig_out rx_model_dqs")
                    deck.append("xrx_dqsn dqs_n_ddr_bga dqs_n_dig_out rx_model_dqs")
                deck.append("")
                
            
            deck.append("*********************************")
            deck.append("****** PKG and Pin Model ********")
            deck.append("*********************************")
            # SoC package model
            thisComp = self.getComp(thisInterface, thisByte.socComp)
            deck.append("* SoC Package Model")
            if not thisComp.r_pkg == '':
                deck.append(".subckt soc_pkg pad pkg_out r2=%s l2=%s c2=%s" % (thisComp.r_pkg, thisComp.l_pkg, thisComp.c_pkg))
            else:
                deck.append(".subckt soc_pkg pad pkg_out r2=100m l2=1.5n c2=0.5p")
            deck.append("R_pkg pad net1 r2")
            deck.append("L_pkg net1 pkg_out l2")
            deck.append("C_pkg pkg_out 0 c2")
            deck.append(".ends")
            deck.append("")
            
            # DDR package model
            thisComp = self.getComp(thisInterface, thisByte.ddrComp)
            deck.append("* DDR Package Model")
            if not thisComp.r_pkg == '':
                deck.append(".subckt ddr_pkg pad pkg_out r1=%s l1=%s c1=%s" % (thisComp.r_pkg, thisComp.l_pkg, thisComp.c_pkg))
            else:
                deck.append(".subckt ddr_pkg pad pkg_out r1=100m l1=1.5nH c1=0.5pF")
            deck.append("R_pkg pad net1 r1")
            deck.append("L_pkg net1 pkg_out l1")
            deck.append("C_pkg pkg_out 0 c1")
            deck.append(".ends")
            deck.append("")
            
            # Pin Parasitic model
            deck.append("* Pin Parasitic Model")
            deck.append(".subckt pin_rlc die_out pin_out rpin=100m lpin=1nH cpin=0.2pF")
            deck.append("R_pin die_out nd_pin1 rpin")
            deck.append("L_pin nd_pin1 pin_out lpin")
            deck.append("C_pin pin_out 0 cpin")
            deck.append(".ends")
            deck.append("")
            
            # Channel model
            deck.append("*********************************")
            deck.append("******** Channel Model **********")
            deck.append("*********************************")
            bytemodelfile = '%s/BYTE%s.sp' %(self.modelPath,  thisByte.byteID )
            if not os.path.isfile(bytemodelfile):
                print('EG02: Cannot find Byte model file.')
                raise SystemExit
            deck.append('.inc "%s"' %(bytemodelfile))
            deck.append("x_channel")
            deck.append("+ dq0_ddr_bga dq1_ddr_bga dq2_ddr_bga dq3_ddr_bga dq4_ddr_bga dq5_ddr_bga dq6_ddr_bga dq7_ddr_bga dqs_p_ddr_bga dqs_n_ddr_bga")
            deck.append("+ dq0_soc_bga dq1_soc_bga dq2_soc_bga dq3_soc_bga dq4_soc_bga dq5_soc_bga dq6_soc_bga dq7_soc_bga dqs_p_soc_bga dqs_n_soc_bga")
            deck.append("+ BYTE%s" %(thisByte.byteID))
            deck.append("")
                
            # Output
            deck.append("*********************************")
            deck.append("*********** Output **************")
            deck.append("*********************************")
            #deck.append(".probe v(dq0_in) v(dq3_in)")
            #deck.append(".probe v(dq0_ddr_bga) v(dq0_soc_bga) v(dqs_p_soc_bga) v(dqs_n_soc_bga) v(dqs_p_ddr_bga) v(dqs_n_ddr_bga)")
            deck.append(".probe v(xrx_dq0.rx_pad) v(xrx_dq1.rx_pad) v(xrx_dq2.rx_pad) v(xrx_dq3.rx_pad) v(xrx_dq4.rx_pad) v(xrx_dq5.rx_pad) v(xrx_dq6.rx_pad) v(xrx_dq7.rx_pad) v(xrx_dqsp.rx_pad, xrx_dqsn.rx_pad)")
            deck.append(".probe v(dq0_dig_out) v(dq1_dig_out) v(dq2_dig_out) v(dq3_dig_out) v(dq4_dig_out) v(dq5_dig_out) v(dq6_dig_out) v(dq7_dig_out)")
            deck.append("")
            deck.append(".print v(xrx_dq0.rx_pad) v(xrx_dq1.rx_pad) v(xrx_dq2.rx_pad) v(xrx_dq3.rx_pad) v(xrx_dq4.rx_pad) v(xrx_dq5.rx_pad) v(xrx_dq6.rx_pad) v(xrx_dq7.rx_pad) v(xrx_dqsp.rx_pad) v(xrx_dqsn.rx_pad)")
            deck.append(".print v(dq0_dig_out) v(dq1_dig_out) v(dq2_dig_out) v(dq3_dig_out) v(dq4_dig_out) v(dq5_dig_out) v(dq6_dig_out) v(dq7_dig_out)")
            deck.append("")
            deck.append(".end")
            
            # Write to file
            outfile = open(deckfile, 'w')
            for line in deck:
                outfile.write('%s\n' % line)
            outfile.close()

    def getComp(self, interface, compName):
        for c in interface.comps:
            if compName == c.compID:
                return c
        return NULL

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

    def parseIbisCompNum(self, ibisFile):
        ibisCompName = []
        with open(ibisFile, 'r') as f:
            for line in f:
                if line.startswith('[model') or line.startswith('[Model'):
                    break
                if line.startswith('[component]') or line.startswith('[Component]'):
                    ibisCompName.append(line.split(' ')[-1].strip())
            return ibisCompName
                
    def parseIbisWhichComp(self, compNameList, thisComp):
        if thisComp.compManufacture.lower() == 'ti':
            logging.debug('D051: Found component match in IBIS file (TI): %s'%(compNameList[0]))
            return compNameList[0]
        else:
            for item in compNameList:
                if thisComp.compPart in item or item in thisComp.compPart:
                    logging.debug('D050: Found component match in IBIS file (Generic): %s'%(item))
                    return item


    def str2num(self, s):
        try:
            num = float(s)
            return num
        except ValueError:  # convert the number with SI Prefix
            s = s.lower()
            unit = re.split(r'(\d+)', s)[-1]
            num = float(s[:-len(unit)])
            scale = unit[0]
            prefix = {  'm' : 1e-3,
                        'u' : 1e-6,
                        'n' : 1e-9,
                        'p' : 1e-12,}
            if scale in prefix.keys():
                return num * prefix[scale]
            else:
                print('E028: Error parsing the SI prefix!')
                return None
        
class DDR:
    def __init__ (self, id):
        self.interfaceID = id
        self.ddrType = ''
        self.dateRate = ''
        self.comps = []
        self.byte = []
        self.ctrl = []
        self.numByte = 0

class Byte:
    def __init__ (self, id):
        self.byteID = id
        self.dq0 = Signal('dq0')
        self.dq1 = Signal('dq1')
        self.dq2 = Signal('dq2')
        self.dq3 = Signal('dq3')
        self.dq4 = Signal('dq4')
        self.dq5 = Signal('dq5')
        self.dq6 = Signal('dq6')
        self.dq7 = Signal('dq7')
        self.dqs_p = Signal('dqs_p')
        self.dqs_n = Signal('dqs_n')
        self.socComp = []
        self.ddrComp = []

class Ctrl:
    def __init__ (self):
        self.addr = []
        self.clk_p = Signal('clk_p')
        self.clk_n = Signal('clk_n')
        self.bank = []
        self.ctrl = []
        self.socComp = []
        self.ddrComp = []
        self.numDDRComp = 0

class Component:
    def __init__ (self, id, part, modelFile, manufacture):
        self.compID = id
        self.compPart = part
        self.compModelFile = modelFile
        self.compManufacture = manufacture
        self.compIbis = IbisModel(self.compID, self.compModelFile)
        self.isDIMM = 0
        self.r_pkg = ''
        self.l_pkg = ''
        self.c_pkg = ''
        
class Signal:
    def __init__ (self, id):
        self.sigID = id
        self.socPin = ''
        self.ddrPin = []
        #self.socModelName = ''
        #self.ddrModelName = []
        self.socModelTx = ''
        self.socModelRx = ''
        self.ddrModelTx = []
        self.ddrModelRx = []

class IbisModel:
    def __init__ (self, comp, fileName):
        self.ibis_designComp = comp
        self.ibis_file = fileName
        self.ibis_comps = []
        self.ibis_pin2selector = {}       # mapping: Pin <-> Model Selector Name
        self.ibis_pin2signal = {}   # mapping: Pin <-> Signal Name
        self.ibis_pin2rpin = {}     # mapping: Pin <-> R_Pin
        self.ibis_pin2lpin = {}     # mapping: Pin <-> L_Pin
        self.ibis_pin2cpin = {}     # mapping: Pin <-> C_Pin
        self.ibis_selector2model = defaultdict(list)     # mapping: Model Selector Name <-> Model Name
        self.ibis_model2type = {}   # mapping: Model <-> Model Type
        self.ibis_model2enable = {} # mapping: Model <-> Enable (Active High/Low)
        
    

if __name__ == "__main__":
    #logging.basicConfig(level=logging.DEBUG)    # uncomment this line to output debug info
    if not len(sys.argv) == 2:
        print('Error! Usage: python3 spgen.py <path_to_interface_folder>')
        raise SystemExit
    projectDir = os.path.abspath(sys.argv[1])
    configFile = 'interface.md'
    thisDesign = Design(projectDir + '/models/' + configFile)    
