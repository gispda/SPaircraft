from gpkit import Model, Variable
from numpy import tan, cos, pi, arctan, arccos
from gpkit.small_scripts import mag
import sys
import numpy as np

def genSolOut(soltable,i = 0):
    f = open('sols/sol' + str(i) + '.out','w')
    f.write(soltable)
    f.close()

def updateOpenVSP(inputDict, i = 0):
    filenameOpen = 'VSP/design.des'
    filenameWrite = 'VSP/design' + str(i) + '.des'

    with open(filenameOpen,'r+') as f:
        g = open(filenameWrite,'w+')
        result = f.read()
        a = result.split('\n')
        outputLines = []
        for line in a:
            words = line.split(':')
            if len(words) > 1:
                key = words[0]
                value = float(words[-1])
                if key in inputDict:
                    value = " " + str(inputDict[key])
                words[-1] = value
            outputLine = ":".join(words)
            outputLines += [outputLine]
        output = '\n'.join(outputLines)
        f.close()
        print('OpenVSP .des output:')
        print(output)
        g.seek(0)
        g.write(output)
        g.truncate()
        g.close()

def gencsm(m, sol, aircraft, i):
    """
    Generates a .csm file (currently only works for 'optimalD8' configuration)
    :param m: an aircraft model (unrelaxed)
    :param sol: solution of that aircraft model
    :param aircraft: string specifying aircraft type
    :param i: numerical ID for output
    :return: None, but saves a .csm in ESP/
    """

    resultsDict = {}
    # Note to make sure that the units are all METRIC
    for key in m.aircraft.design_parameters.iterkeys():
        resultsDict[key] = mag(sol(m.aircraft.design_parameters[key]))
    f = open('ESP/d82-' + str(i) + '.csm', 'w')
    f.write("""# D8.2 aircraft
# autogenerated CSM file

# Constant and Design Parameters:

""")
    for key in resultsDict.keys():
        f.write("despmtr   %s   %s\n" % (key, resultsDict[key]))
    f.write("""
# Writing out fuselage hyperellipse coordinates (normalized by Rfuse+0.5dRfuse and wfuse)
dimension fuse      20  4  1
#        x                    radius in y       radius in z       camberLine            
despmtr fuse "0.0100000000000000;   0.231620320814217; 0.201788367337146; 0.415017595384628; \\
         0.0167511548156525;   0.303329825633191; 0.286800005551124; 0.432707096855554; \\
         0.0368204653581859;   0.465089555398346; 0.401402957687781; 0.391348086609170; \\
         0.0696604931527879;   0.639984339778467; 0.547053945092908; 0.336554479448422; \\
         0.114375447848785;    0.796914808663171; 0.690750012181914; 0.253564929286064; \\
         0.169745622045258;    0.918299891822636; 0.831913960689778; 0.145967817033052; \\
         0.234260661729399;    0.989572852786478; 0.940058547054229; 0.052165172147333; \\
         0.306160764796780;    0.999585285603803; 0.989558928335193; 0.0089841549140855; \\
         0.383484683865304;    0.999828050247791; 0.999895739428622; 0.0000001; \\
         0.464123223991196;    0.999835846523687; 0.999992038455302; 0.00000001; \\
         0.545876776008805;    0.999837104793590; 0.999992459108003; 0.00000001; \\
         0.626515316134696;    0.999836691312273; 1.000000000000;    0.000001; \\
         0.703839235203220;    0.999837116939711; 0.971402993194143; 0.0142164604347808; \\
         0.775739338270601;    1.0;               0.817680916438905; 0.0387447426776049; \\
         0.840254377954742;    0.966048629717998; 0.555797975170839; -0.001751049892089; \\
         0.895624552151215;    0.882868686664148; 0.310547207226524; -0.042810120752847; \\
         0.940339506847212;    0.795619028833805; 0.148753911080915; -0.052495746822761; \\
         0.973179534641814;    0.726999772783226; 0.057314226903622; -0.056768317278699; \\
         0.993248845184348;    0.683847989903762; 0.012920345779019; -0.058890618333758; \\
         1.0;                  0.669124268823783; 0.0;               -0.05918874470713;" \\

# Writing out fuselage hyperellipse coordinates (normalized by Rfuse+0.5dRfuse and wfuse)
dimension fuseExp      1 10 1
dimension fuseProp     1 10 1
dimension fusehmod     1 10 1
dimension fusewmod     1 10 1
despmtr fuseExp     "0.0; 0.2; 1.5; 3.0; 3.8; 3.8; 2.9; 1.2; 0.2; 0.0"
despmtr fuseProp    "0.0; 0.1; 0.2; 0.3; 0.4; 0.5; 0.6; 0.7; 0.8; 0.9"
despmtr fusehmod    "0.98; 0.98; 0.98; 0.98; 0.98; 0.98; 0.98; 0.9; 0.8; 0.5"
despmtr fusewmod    "0.98; 0.98; 0.98; 0.98; 0.98; 0.98; 0.98; 0.98; 0.9; 0.8"

# Global Attributes:

# Branches:
set       pxnose fuselage:lnose/fuselage:lfuse
set       pxcone 1.-fuselage:lcone/fuselage:lfuse
set       lcyl fuselage:lfuse*(pxcone-pxnose)
set       lshell2 pxcone*fuselage:lfuse
set       dRx1 fuselage:wdb+fuselage:Rfuse/2+fuselage:dRfuse/2
set       dRx2 fuselage:wdb+fuselage:Rfuse/2
set       dRz1 -1*(fuselage:Rfuse+fuselage:dRfuse/2)
set       dRz2 -1*(fuselage:Rfuse+fuselage:dRfuse)
set       wfuseTE 1.6*fuselage:wfuse
set       wing:dihedral 6.
set       vt:dihedralvt 10. 
set       wing:sweep atand(wing:tanw)
set       vt:sweepvt atand(vt:tanvt)
set       ht:sweepht atand(ht:tanht)


# Building the fuselage
mark
point     0  0  fuse[1,4]*fuselage:hfuse

patbeg    i  19
   udprim ellipse   rx  abs(fuse[i,2]*fuselage:wfuse)  rz  abs(fuse[i,3]*fuselage:hfuse)
   translate        0     fuse[i,1]*fuselage:lfuse     fuse[i,4]*fuselage:hfuse   
patend

# Add final line for sharp TE
#skbeg     fuse[19,2]*fuselage:wfuse      fuse[19,1]*fuselage:lfuse     fuse[19,4]*hfuse
#linseg   -fuse[19,2]*fuselage:wfuse      fuse[19,1]*fuselage:lfuse     fuse[19,4]*hfuse
#linseg   fuse[19,2]*fuselage:wfuse      fuse[19,1]*fuselage:lfuse     fuse[19,4]*hfuse
#skend
blend 0

rotatez 270 0 0

# Building the wing
despmtr   series_w  4409
set xleadwroot   wing:xwing-wing:croot/4
set xleadwtip    xleadwroot+wing:b/2*tand(wing:sweep)
set zleadwroot   -0.8*fuselage:Rfuse  # Arbitrary wing height
#set zleadwtip    zleadwroot+sind(wing:dihedral)*halfspan
set halfspan     wing:b/2

mark
udprim     naca     Series     series_w sharpte 1
scale wing:ctip
rotatex 90 0 0 
translate xleadwtip -halfspan zleadwroot+sind(wing:dihedral)*halfspan            
udprim     naca     Series     series_w sharpte 1
scale wing:croot
rotatex 90 0 0
translate xleadwroot 0 zleadwroot
udprim     naca     Series     series_w sharpte 1
scale wing:ctip
rotatex 90 0 0 
translate xleadwtip halfspan zleadwroot+sind(wing:dihedral)*halfspan
rule
union

# Adding fuselage/wing blending 
mark 

patbeg i 10
   udprim supell rx fusewmod[1,i]*fuselage:wfuse-0.01 ry fusehmod[1,i]*fuselage:hfuse-0.01 n_sw fuseExp[1,i]+1 n_se fuseExp[1,i]+1 n_nw 1 n_ne 1 
   rotatey 90 0 0 
   rotatex 90 0 0
   translate fuseProp[1,i]*2.5*wing:croot+wing:xwing-0.75*wing:croot   0   0
patend
blend

# Building the vertical tail
despmtr   series_vt  0009
set xleadvtroot   fuselage:lfuse-vt:crootvt
set xleadvttip    xleadvtroot+vt:bvt*cosd(vt:sweepvt)
set yleadvtroot   0.67*fuselage:wfuse-0.045*vt:crootvt # Note this depends on af toc
set yleadvttip    yleadvtroot+sind(vt:dihedralvt)*vt:bvt
set zleadvtroot   fuse[19,4]*fuselage:hfuse
set zleadvttip    zleadvtroot+(cosd(vt:dihedralvt))*vt:bvt


mark
udprim     naca     Series     series_vt sharpte 1
scale vt:ctipvt
rotatex vt:dihedralvt 0 0
translate xleadvttip yleadvttip zleadvttip             
udprim     naca     Series     series_vt sharpte 1
scale vt:crootvt
rotatex vt:dihedralvt 0 0
translate xleadvtroot yleadvtroot zleadvtroot
rule
#union

mark
udprim     naca     Series     series_vt sharpte 1
scale vt:ctipvt
rotatex -vt:dihedralvt 0 0
translate xleadvttip -yleadvttip zleadvttip             
udprim     naca     Series     series_vt sharpte 1
scale vt:crootvt
rotatex -vt:dihedralvt 0 0
translate xleadvtroot -yleadvtroot zleadvtroot
rule
#union

# Building the horizontal tail
despmtr   series_ht  2209
set xleadhtroot   xleadvttip-tand(ht:sweepht)*yleadvttip
set xleadhttip    xleadhtroot+ht:bht/2.*tand(ht:sweepht)
set yleadhtroot   0
set yleadhttip    ht:bht/2
set zleadhtroot   zleadvttip #TODO improve
set zleadhttip    zleadvttip #TODO improve

mark
udprim     naca     Series     series_ht sharpte 1
scale ht:ctipht
rotatex 90 0 0 
translate xleadhttip yleadhttip zleadhttip
udprim     naca     Series     series_ht sharpte 1
scale ht:crootht
rotatex 90 0 0
translate xleadhtroot yleadhtroot zleadhtroot
udprim     naca     Series     series_ht sharpte 1
scale ht:ctipht
rotatex 90 0 0 
translate xleadhttip -yleadhttip zleadhttip
rule

end""")
    f.close()
    print('File generation successful!')

def gendes(m, sol, aircraft = 'optimalD8', i = 0):
    sweep = arccos(sol('\cos(\Lambda)_Mission/Aircraft/Wing/WingNoStruct'))*180/np.pi

    # System-level descriptors
    xCG = sol('x_{CG}')[0].to('m')

    # Wing descriptors
    b = sol('b').to('m')
    croot = sol('c_{root}').to('m')
    ctip = sol('c_{tip}').to('m')
    S = sol('S').to('m^2')
    xwing = sol('x_{wing}').to('m')
    dihedral = 6.

    # Fuselage descriptors
    hfloor = sol('h_{floor}_Mission/Aircraft/Fuselage').to('m')
    lnose = sol('l_{nose}_Mission/Aircraft/Fuselage').to('m')
    lshell = sol('l_{shell}').to('m')
    lcone = sol('l_{cone}').to('m')
    lfloor = sol('l_{floor}').to('m')
    lfuse = sol('l_{fuse}').to('m')
    hfuse = sol('h_{fuse}').to('m')
    wfuse = sol('w_{fuse}').to('m')
    wfloor = sol('w_{floor}').to('m')
    wdb = sol('w_{db}_Mission/Aircraft/Fuselage').to('m')
    Rfuse = sol('R_{fuse}_Mission/Aircraft/Fuselage').to('m')
    dRfuse = sol('\\Delta R_{fuse}_Mission/Aircraft/Fuselage').to('m')

    # Horizontal Tail descriptors
    xCGht = sol('x_{CG_{ht}}').to('m')
    crootht = sol('c_{root_{ht}}').to('m')
    ctipht = sol('c_{tip_{ht}}').to('m')
    dxleadht = sol('\\Delta x_{lead_{ht}}').to('m')
    dxtrailht = sol('\\Delta x_{trail_{ht}}').to('m')
    bht = sol('b_{ht}').to('m')
    xCGht = sol('x_{CG_{ht}}').to('m')
    lht = sol('l_{ht}').to('m')
    tanht = sol('\\tan(\Lambda_{ht})_Mission/Aircraft/HorizontalTail/HorizontalTailNoStruct')

    # Vertical Tail descriptors
    xCGvt = sol('x_{CG_{vt}}').to('m')
    Svt = sol('S_{vt}').to('m^2')
    bvt = sol('b_{vt}').to('m')
    lvt = sol('l_{vt}').to('m')
    crootvt = sol('c_{root_{vt}}').to('m')
    ctipvt = sol('c_{tip_{vt}}').to('m')
    dxleadvt = sol('\\Delta x_{lead_{vt}}').to('m')
    dxtrailvt = sol('\\Delta x_{trail_{vt}}').to('m')
    tanvt = sol('\\tan(\Lambda_{vt})_Mission/Aircraft/VerticalTail/VerticalTailNoStruct')

    # Engine descriptors
    df = sol('d_{f}_Mission/Aircraft/Engine').to('m') # Engine frontal area
    lnace = sol('l_{nacelle}').to('m')
    yeng = sol('y_{eng}_Mission/Aircraft/VerticalTail/VerticalTailNoStruct').to('m')
    xeng = sol('x_{eng}').to('m')

# Creating the default (D82) resultsDict
    resultsDict = {
        # Engine Variables
        'OOWZWGGROQZ':float(lnace.magnitude),   # Engine length (chord)
        'TTRJCLVSWWP':float(df.magnitude + 0.1625/2.*lnace.magnitude),       # Engine height
        'YUWFYBTYKTL':float(0.1625),             # Engine airfoil thickness/chord
        'TVQVWMMVRYB':float(df.magnitude + 0.1625/2.*lnace.magnitude),       # Engine width
        'EGCVYPSLWEZ':float(xeng.magnitude - 0.5*lnace.magnitude),    # Engine x location
        'RJLYSBJAFOT':float(yeng.magnitude),     #Engine y location
        'GBGVQARDEVD':float(hfuse.magnitude - (df/5.).magnitude), # Engine z location
        'HKVDGHIEXRW':float(15.),                                  # Engine up-rotation (degrees)

        # Floor Variables
        'MCVUEHMJBGG':float(hfloor.magnitude),  # Floor height
        'EVDJZIXRYSR':float(lfloor.magnitude), # Floor length
        'SKXVOFXEYEZ':float(2*wfloor.magnitude), # Floor width
        'KNNNINRHVVJ':float(lnose.magnitude-Rfuse.magnitude), # Floor x location (beginning of cyl section)
        'AFIOFOUHMWM':float(-0.5 - 0.5*hfloor.magnitude), # Floor z location (offset from thickest section)

        # Fuselage variables
        'HOVDTKFGFQC':float(lfuse.magnitude), # Fuselage length
        'KBKZBHMUHEP':float((lnose/lfuse).magnitude), # Nose location as % of fuse length
        'OVEJIBRDSBJ':float(1. - (lcone/lfuse).magnitude), # Tailcone location as % of fuse length
        'JMWPVNGZBYQ':float(2.0*hfuse.magnitude), # Fuselage height
        'KFWNCSRQOCQ':float(2*wfuse.magnitude), # Fuselage width
        'WKRLDITVGSF':float(2.0*hfuse.magnitude), # Fuselage height
        'TBCZTWFMJDM':float(2*wfuse.magnitude), # Fuselage width
        'JOBWSWPMZIB':float(2.0*hfuse.magnitude), # Fuselage height
        'HPKOTUWYSIY':float(2*wfuse.magnitude), # Fuselage width
        'GCQLYPQAIGM':float(0.8*2*wfuse.magnitude), # Fuselage width (for DB line trailing edge).


        # HT Variables
        'USGQFZQKJWC':float(xCG.magnitude + dxleadht.magnitude), # HT x location
        'BLMHVDOLAQJ':float(0.5 + bvt.magnitude), # HT z location
        'IFZAMYYJPRP':float(arctan(tanht)*180/pi), # HT sweep
        'CHYQUCYJMPS':float(bht.magnitude*0.5), # HT half-span
        'LQXJHZEHDRX':float(crootht.magnitude), # HT root chord
        'AYFSAELIRAY':float(ctipht.magnitude), # HT tip chord

        # VT variables
        'LLYTEYDPDID':float(xCG.magnitude + dxleadvt.magnitude), # VT x location (LE location)
        'BFZDOVCXTAV':float(wfuse.magnitude),                    # VT y location (as wide as fuselage)
        'FQDVQTUBLUX':float(0.5),                                  # VT z location (0.5 m off the widest point of the fuselage)
        'JXFRWSLYWDH':float(bvt.magnitude),                        # VT span
        'MBZGSEIYFGW':float(crootvt.magnitude),                    # VT root chord
        'CUIMIUZJQMS':float(ctipvt.magnitude),                     # VT tip chord
        'XLPAIOGKILI':float(arctan(tanvt)*180/pi),                 # VT sweep angle
        'GWTZZGTPXQU':-10,                                          # VT dihedral

        # Wing variables
        'AYJHHOVUHBI':float(b.magnitude*0.5), # Wing half-span
        'UOBOGEWYYZZ':float((xwing - 0.25*croot).magnitude), # Wing x-location
        'MOGKYBMVMPD':float(-1*hfuse.magnitude + 0.2), # Wing z-location
        'NNIHPEXRTCP':float(croot.magnitude), # Wing root chord
        'HGZBRNOPIRD':float(ctip.magnitude), # Wing tip chord
        'AGOKGLSLBTO':float(sweep), # Wing sweep angle
        'SMCAVCZXJSG':float(+dihedral), # Wing dihedral
    }
    # if aircraft in ['D8big', 'D82_73eng', 'D8_eng_wing', 'optimalD8', 'M08D8', 'M08_D8_eng_wing']:

    # Wing mounted engines
    if aircraft in ['D8_eng_wing','optimal737','optimal777']:
        resultsDict.update({
         # Engine Variables
        'GBGVQARDEVD':float(-hfuse.magnitude - 0.2*df.magnitude), # Engine z location
        'HKVDGHIEXRW':float(0.),                                  # Engine up-rotation (degrees)
        })
    # Conventional tail
    if aircraft in ['optimal737','optimal777']:
        resultsDict.update({
        # HT Variables
        'BLMHVDOLAQJ':float(0.),                                             # HT z location
        'CHYQUCYJMPS':float(bht.magnitude*0.5 + wfuse.magnitude),            # HT half-span

        # VT variables
        'BFZDOVCXTAV':float(0.),                           # VT y location (as wide as fuselage)
        'FQDVQTUBLUX':float(0.),                           # VT z location (0.5 m off the widest point of the fuselage)
        'GWTZZGTPXQU':float(0.),                           # VT dihedral

        # Fuselage variables
        'GCQLYPQAIGM':float(0.),
    })
    # Rear mounted non-BLI D8 engines
    if aircraft in ['D8_no_BLI']:
        resultsDict.update({
        'GBGVQARDEVD':float(0.0), # Engine z location
    })

    updateOpenVSP(resultsDict,i)
    print('File generation successful!')

# def gencsm()
#     # Wing mounted engines
#         if aircraft in ['D8_eng_wing','optimal737','optimal777']:
#             resultsDict.update({
#              # Engine Variables
#             'engine:zeng':float(-0.5*hfuse.magnitude - 0.2*df.magnitude), # Engine z location
#             'engine:zup':float(0.),                                  # Engine up-rotation (degrees)
#             })
#         # Conventional tail
#         if aircraft in ['optimal737','optimal777']:
#             resultsDict.update({
#             # HT Variables
#             'ht:zht':float(0.),                                             # HT z location
#             'ht:bht':float(bht.magnitude + 2*wfuse.magnitude),            # HT half-span
#
#             # VT variables
#             'vt:yvt':float(0.),                           # VT y location (as wide as fuselage)
#             'vt:zvt':float(0.),                           # VT z location (0.5 m off the widest point of the fuselage)
#             'vt:dihedralvt':float(0.),                           # VT dihedral
#             })
#         # Rear mounted non-BLI D8 engines
#         if aircraft in ['D8_no_BLI']:
#             resultsDict.update({
#                 'engine:zeng':float(0.0), # Engine z location
#             })
