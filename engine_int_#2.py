"""Simple commercial aircraft flight profile and aircraft model"""
""" Combines Wing, VerticalTail, and Fuselage models for D8"""
from numpy import pi, cos, tan
import numpy as np
from gpkit import Variable, Model, units, SignomialsEnabled, SignomialEquality, Vectorize
from gpkit.tools import te_exp_minus1
from gpkit.constraints.tight import Tight as TCS
TCS.reltol = 1e-3

from gpkit.constraints.bounded import Bounded as BCS

# only needed for the local bounded debugging tool
from collections import defaultdict
from gpkit.small_scripts import mag

# only needed for plotting
import matplotlib.pyplot as plt

# importing from D8_integration
from stand_alone_simple_profile import FlightState, Altitude, Atmosphere
from D8_VT_yaw_rate_and_EO_simple_profile import VerticalTail, VerticalTailPerformance
from D8_HT_simple_profile import HorizontalTail, HorizontalTailPerformance
from Wing_simple_performance import Wing, WingPerformance
from TASOPT_engine import Engine

sweep = 30

"""
Models requird to minimize the aircraft total fuel weight. Rate of climb equation taken from John
Anderson's Aircraft Performance and Design (eqn 5.85).
Inputs
-----
- Number of passengers
- Passenger weight [N]
- Fuselage area per passenger (recommended to use 1 m^2 based on research) [m^2]
- Engine weight [N]
- Number of engines
- Required mission range [nm]
- Oswald efficiency factor
- Max allowed wing span [m]
- Cruise altitude [ft]
Sources for substitutions:
-[b757 freight doc]
-[Boeing]
-[Philippe]
-[stdAtm]
-[TAS]
Other markers:
-[SP]
-[SPEquality]
"""

# Script for doing sweeps
n = 10
sweeps = False
sweepSMmin = True
sweepdxCG = True
sweepReqRng = False
sweepthetadb = False
sweepxCG = False
sweepCruiseAlt = False
sweepW_engine = True

plot = True

g = 9.81 * units('m*s**-2')

class Aircraft(Model):
    "Aircraft class"

    def setup(self, Nclimb, Ncruise, enginestate, **kwargs):
        # create submodels
        self.fuse = Fuselage()
        self.wing = Wing()
        self.VT = VerticalTail()
        self.HT = HorizontalTail()
        self.engine = Engine(0, True, Nclimb + Ncruise, enginestate)

        # variable definitions
        numeng = Variable('numeng', '-', 'Number of Engines')
        Vne = Variable('V_{ne}',144, 'm/s', 'Never-exceed speed')  # [Philippe]
        rhoTO = Variable('\\rho_{T/O}',1.225,'kg*m^-3','Air density at takeoff')
        
        SMmin = Variable('SM_{min}','-', 'Minimum Static Margin')
        dxCG = Variable('\\Delta x_{CG}', 'm', 'Max CG Travel Range')
        xCGmin = Variable('x_{CG_{min}}','m','Maximum Forward CG')

        constraints = []
        with SignomialsEnabled():
            constraints.extend([
                            self.wing['c_{root}'] == self.fuse['c_0'],
                            self.wing.wb['wwb'] == self.fuse['wtc'],
                            self.wing['x_w'] == self.fuse['x_{wing}'],
                            self.wing['V_{ne}'] == 144*units('m/s'),
                            self.VT['V_{ne}'] == 144*units('m/s'),

                            # Tail cone sizing
                            3 * self.VT['M_r'] * self.VT['c_{root_{vt}}'] * \
                                (self.fuse['p_{\\lambda_v}'] - 1) >= self.VT[
                                    'L_{v_{max}}'] * self.VT['b_{vt}'] * (self.fuse['p_{\\lambda_v}']),
                            TCS([self.fuse['V_{cone}'] * (1 + self.fuse['\\lambda_{cone}']) * \
                             (pi + 4 * self.fuse['\\theta_{db}']) >= 2*self.VT[
                                'M_r'] * self.VT['c_{root_{vt}}'] / self.fuse['\\tau_{cone}'] * \
                                 (pi + 2 * self.fuse['\\theta_{db}']) * \
                                  (self.fuse['l_{cone}'] / self.fuse['R_{fuse}'])]), #[SP]

                            # Tail weight
                            self.fuse['W_{tail}'] >= 2*self.VT['W_{struct}'] + \
                                self.HT['W_{struct}'] + self.fuse['W_{cone}'],

                            # Horizontal tail aero loads constant A1h
                            self.fuse['A1h'] >= (self.fuse['N_{land}'] * \
                                                 (self.fuse['W_{tail}'] + numeng*self.engine['W_{engine}'] + self.fuse['W_{apu}']) \
                                + self.fuse['r_{M_h}'] * self.HT['L_{{max}_h}']) / \
                                 (self.fuse['h_{fuse}'] * self.fuse['\\sigma_{M_h}']),

                            # Lift curve slope ratio for HT and Wing
                            SignomialEquality(self.HT['m_{ratio}']*(1+2/self.wing['AR']), 1 + 2/self.HT['AR_h']),

                            # HT Location and Volume Coefficient
                            self.HT['x_{CG_{ht}}'] <= self.fuse['l_{fuse}'],
                            self.fuse['x_{tail}'] == self.VT['x_{CG_{vt}}'],
                            TCS([self.HT['V_{h}'] == self.HT['S_h']*self.HT['l_{ht}']/(self.wing['S']*self.wing['mac'])]),
                            # self.HT['V_{h}'] >= 0.4,

                            # HT Max Loading
                            TCS([self.HT['L_{{max}_h}'] >= 0.5*rhoTO*Vne**2*self.HT['S_h']*self.HT['C_{L_{hmax}}']]),

                            # HT/VT joint constraint
                            self.HT['b_{ht}']/self.fuse['w_{fuse}']*self.HT['\lambda_h']*self.HT['c_{root_h}'] == self.HT['c_{attach}'],

                            # VT height constraint (4*engine radius)
                            self.VT['b_{vt}']**2 >= 16.*self.engine['A_2']/np.pi,

                            # VT root chord constraint #TODO find better constraint
                            self.VT['c_{root_{vt}}'] <= self.fuse['l_{cone}'],

                            # Engine out moment arm,
                            self.VT['y_{eng}'] == 0.25*self.fuse['w_{fuse}'],

                            ])

        self.components = [self.fuse, self.wing, self.VT, self.HT, self.engine]

        return self.components, constraints

    def climb_dynamic(self, state, Nsplit):
        """
        creates an aircraft climb performance model, given a state
        """
        return ClimbP(self, state, Nsplit)

    def cruise_dynamic(self, state, Nsplit):
        """
        creates an aircraft cruise performance model, given a state
        """
        return CruiseP(self, state, Nsplit)


class AircraftP(Model):
    """
    Aircraft performance models superclass, contains constraints true for
    all flight segments
    """

    def setup(self, aircraft, state):
        # make submodels
        self.aircraft = aircraft
        self.wingP = aircraft.wing.dynamic(state)
        self.fuseP = aircraft.fuse.dynamic(state)
        self.VTP = aircraft.VT.dynamic(aircraft.fuse,state)
        self.HTP = aircraft.HT.dynamic(aircraft.fuse,aircraft.wing,state)
        self.Pmodels = [self.wingP, self.fuseP, self.VTP, self.HTP]

        # variable definitions
        Vstall = Variable('V_{stall}',120, 'knots', 'Aircraft Stall Speed')
        D = Variable('D', 'N', 'Total Aircraft Drag')
        W_avg = Variable(
            'W_{avg}', 'N', 'Geometric Average of Segment Start and End Weight')
        W_start = Variable('W_{start}', 'N', 'Segment Start Weight')
        W_end = Variable('W_{end}', 'N', 'Segment End Weight')
        W_burn = Variable('W_{burn}', 'N', 'Segment Fuel Burn Weight')
        WLoadmax = Variable('W_{Load_max}',6664, 'N/m^2', 'Max Wing Loading')
        WLoad = Variable('W_{Load}', 'N/m^2', 'Wing Loading')
        t = Variable('tmin', 'min', 'Segment Flight Time in Minutes')
        thours = Variable('thr', 'hour', 'Segment Flight Time in Hours')

        xAC = Variable('x_{AC}','m','Aerodynamic Center of Aircraft')
        xCG = Variable('x_{CG}','m','Center of Gravity of Aircraft')

        Pcabin = Variable('P_{cabin}','Pa','Cabin Air Pressure')
        W_buoy = Variable('W_{buoy}','lbf','Buoyancy Weight')
        Tcabin = Variable('T_{cabin}','K','Cabin Air Temperature')
        rhocabin = Variable('rho_{cabin}','kg/m^3','Cabin Air Density')

        constraints = []

        with SignomialsEnabled():
            constraints.extend([
            # Cabin Air properties
            rhocabin == Pcabin/(state['R']*Tcabin),
            Pcabin == 75000*units('Pa'),
            Tcabin == 297*units('K'),

            # Buoyancy weight
            SignomialEquality(W_buoy,(rhocabin - state['\\rho'])*g*aircraft['V_{cabin}']),

            # speed must be greater than stall speed
            state['V'] >= Vstall,

            # compute the drag
            D >= self.wingP['D_{wing}'] + self.fuseP['D_{fuse}'] + self.VTP['D_{vt}'] + self.HTP['D_{ht}'],

            # Wing looading
            WLoad == .5 * self.wingP['C_{L}'] * self.aircraft['S'] * state.atm['\\rho'] * state['V']**2 / self.aircraft.wing['S'],

            # Geometric average of start and end weights of flight segment
            W_avg == (W_start * W_end)**.5,

            # Maximum wing loading constraint
            WLoad <= WLoadmax,

            # Flight time unit conversion
            t == thours,

            #VTP constraints
            TCS([aircraft.fuse['l_{fuse}'] >= aircraft.VT['\\Delta x_{trail_v}'] + xCG]),
            TCS([aircraft.VT['x_{CG_{vt}}'] >= xCG + (aircraft.VT['\\Delta x_{lead_v}']+aircraft.VT['\\Delta x_{trail_v}'])/2]),
            aircraft.VT['x_{CG_{vt}}'] <= aircraft.fuse['l_{fuse}'],

            # Drag of a windmilling engine (VT sizing)
            TCS([aircraft.VT['D_{wm}'] >= 0.5*aircraft.VT['\\rho_{TO}']*aircraft.VT['V_1']**2*self.aircraft.engine['A_2']*aircraft.VT['C_{D_{wm}}']]),

            # Center of gravity constraints #TODO Refine
            xCG <= 0.7*aircraft.fuse['l_{fuse}'],
            xCG >= aircraft['x_{CG_{min}}'],
            xAC >= xCG,

            # Wing location constraints
            aircraft.fuse['x_{wing}'] >= aircraft.fuse['l_{fuse}']*0.5, #TODO remove
            aircraft.fuse['x_{wing}'] <= aircraft.fuse['l_{fuse}']*0.6, #TODO remove

            # Aircraft trim conditions
            # SignomialEquality(xAC/aircraft.wing['mac'],  self.wingP['c_{m_{w}}']/self.wingP['C_{L}'] + xCG/aircraft.wing['mac'] + \
            #                   aircraft.HT['V_{h}']*(self.HTP['C_{L_h}']/self.wingP['C_{L}'])),
            TCS([xAC/aircraft.wing['mac'] <= self.wingP['c_{m_{w}}']/self.wingP['C_{L}'] + xCG/aircraft.wing['mac'] + \
                              aircraft.HT['V_{h}']*(self.HTP['C_{L_h}']/self.wingP['C_{L}'])]),

            # Tail aspect ratio and lift constraints
            aircraft.HT['AR_h'] >= 6, #TODO change to tip Re constraint
            self.HTP['C_{L_h}'] >= 0.01, #TODO remove
            aircraft.VT['A_{vt}'] >= 1.5,

            # HT/VT moment arm constraints
            TCS([aircraft.HT['l_{ht}'] <= aircraft.HT['x_{CG_{ht}}'] - xCG]),
            TCS([aircraft.VT['l_{vt}'] <= aircraft.VT['x_{CG_{vt}}'] - xCG]),

           # Tail downforce penalty to wing lift
            self.wingP['L_w'] >= W_avg + self.HTP['L_h'],

            # Wing location and AC constraints
            TCS([xCG + self.HTP['\\Delta x_{{trail}_h}'] <= aircraft.fuse['l_{fuse}']]), #TODO tighten
            xAC == aircraft['x_{wing}'], #TODO improve, only works because cmw == 0.1
            SignomialEquality(xAC,xCG + self.HTP['\\Delta x_w']),

            TCS([aircraft.HT['x_{CG_{ht}}'] >= xCG + 0.5*(self.HTP['\\Delta x_{{trail}_h}'] + self.HTP['\\Delta x_{{lead}_h}'])]), #TODO tighten

            # Static margin constraint with and without dxCG #TODO validate if this works as intended
            self.wingP['c_{m_{w}}'] == 0.1,
            TCS([aircraft['SM_{min}'] + aircraft['\\Delta x_{CG}']/aircraft.wing['mac'] <=
                                            aircraft.HT['V_{h}']*aircraft.HT['m_{ratio}'] \
                                          + self.wingP['c_{m_{w}}']/aircraft.wing['C_{L_{wmax}}'] + \
                                            aircraft.HT['V_{h}']*aircraft.HT['C_{L_{hmax}}']/aircraft.wing['C_{L_{wmax}}']]), # [SP]
            # TCS([aircraft['SM_{min}'] <=
            #                                 aircraft.HT['V_{h}']*aircraft.HT['m_{ratio}'] \
            #                               + self.wingP['c_{m_{w}}']/aircraft.wing['C_{L_{wmax}}'] + \
            #                                 aircraft.HT['V_{h}']*aircraft.HT['C_{L_{hmax}}']/aircraft.wing['C_{L_{wmax}}']]), # [SP]

            # SignomialEquality(SM + aircraft['\\Delta x_{CG}']/aircraft.wing['mac'],
            #                                 aircraft.HT['V_{h}']*aircraft.HT['m_{ratio}'] \
            #                               + self.wingP['c_{m_{w}}']/aircraft.wing['C_{L_{wmax}}'] + \
            #                                 aircraft.HT['V_{h}']*aircraft.HT['C_{L_{hmax}}']/aircraft.wing['C_{L_{wmax}}']),
           ])

        return self.Pmodels, constraints


class ClimbP(Model): # Climb performance constraints

    def setup(self, aircraft, state, Nsplit, **kwargs):
        # submodels
        self.aircraft = aircraft
        self.aircraftP = AircraftP(aircraft, state)

        # variable definitions
        theta = Variable('\\theta', '-', 'Aircraft Climb Angle')
        excessP = Variable('excessP', 'W', 'Excess Power During Climb')
        RC = Variable('RC', 'feet/min', 'Rate of Climb/Decent')
        dhft = Variable(
            'dhft', 'feet', 'Change in Altitude Per Climb Segment [feet]')
        RngClimb = Variable('RngClimb', 'nautical_miles',
                            'Down Range Covered in Each Climb Segment')
        # Fsub = Variable('Fsub','N','Thrust substitution for climb')

        # constraints
        constraints = []

        constraints.extend([
            # Thrust >= Drag + Vertical Potential Energy
            self.aircraft['numeng'] * self.aircraft.engine['F'][:Nsplit] >= self.aircraftP[
                'D'] + self.aircraftP['W_{avg}'] * theta,
            # self.aircraft['numeng'] * Fsub >= self.aircraftP[
            #     'D'] + self.aircraftP['W_{avg}'] * theta,

            # Excess power for climb
            TCS([excessP + state['V'] * self.aircraftP['D'] <= \
                 state['V'] * self.aircraft['numeng'] * self.aircraft.engine['F'][:Nsplit]]),
            # TCS([excessP + state['V'] * self.aircraftP['D'] <= \
            #      state['V'] * self.aircraft['numeng'] * Fsub]),

            RC == excessP / self.aircraftP['W_{avg}'],
            RC >= 500 * units('ft/min'),

            # Fsub[0] == 63.*units('kN'),
            # Fsub[1] == 45.*units('kN'),

            # Climb angle and rate constraint
            theta * state['V'] == RC,

            dhft == self.aircraftP['tmin'] * RC,

            # Small angle assumption during climb
            RngClimb == self.aircraftP['thr'] * state['V'],

            #Fuel burn computation
            self.aircraftP['W_{burn}'] == self.aircraft['numeng'] * self.aircraft.engine['TSFC'][:Nsplit] * \
            self.aircraftP['thr'] * self.aircraft.engine['F'][:Nsplit],
        ])

        return constraints + self.aircraftP


class CruiseP(Model): # Cruise performance constraints

    def setup(self, aircraft, state, Nsplit, **kwargs):
        self.aircraft = aircraft
        self.aircraftP = AircraftP(aircraft, state)

        # variable definitions
        z_bre = Variable('z_{bre}', '-', 'Breguet Parameter')
        Rng = Variable('Rng', 'nautical_miles', 'Cruise Segment Range')

        constraints = []

        constraints.extend([
            # Steady level flight constraint on D
            self.aircraftP['D'] == aircraft[
                'numeng'] * aircraft['F'][Nsplit:],

            # Taylor series expansion to get the weight term
            TCS([self.aircraftP['W_{burn}'] / self.aircraftP['W_{end}'] >=
                 te_exp_minus1(z_bre, nterm=3)]),

            # Breguet range eqn
            TCS([z_bre >= (aircraft.engine['TSFC'][Nsplit:] * self.aircraftP['thr'] *
               self.aircraftP['D']) / self.aircraftP['W_{avg}']]),

            # Time
            self.aircraftP['thr'] * state['V'] == Rng,

            # Fuel burn computation
            self.aircraftP['W_{burn}'] == aircraft['numeng'] * aircraft.engine['TSFC'][Nsplit:] * \
            self.aircraftP['thr'] * aircraft.engine['F'][Nsplit:],
        ])

        return constraints + self.aircraftP


class CruiseSegment(Model):
    """
    Combines a flight state and aircrat to form a cruise flight segment
    """

    def setup(self, aircraft, Nsplit, **kwargs):
        self.state = FlightState()
        self.cruiseP = aircraft.cruise_dynamic(self.state, Nsplit)

        return self.state, self.cruiseP


class ClimbSegment(Model):
    """
    Combines a flight state and aircrat to form a cruise flight segment
    """

    def setup(self, aircraft, Nsplit, **kwargs):
        self.state = FlightState()
        self.climbP = aircraft.climb_dynamic(self.state, Nsplit)

        return self.state, self.climbP

class StateLinking(Model):
    """
    link all the state model variables
    """
    def setup(self, climbstate, cruisestate, enginestate, Nclimb, Ncruise):
        statevarkeys = ['p_{sl}', 'T_{sl}', 'L_{atm}', 'M_{atm}', 'P_{atm}', 'R_{atm}',
                        '\\rho', 'T_{atm}', '\\mu', 'T_s', 'C_1', 'h', 'hft', 'V', 'a', 'R', '\\gamma', 'M']
        constraints = []
        for i in range(len(statevarkeys)):
            varkey = statevarkeys[i]
            for i in range(Nclimb):
                constraints.extend([
                    climbstate[varkey][i] == enginestate[varkey][i]
                    ])
            for i in range(Ncruise):
                constraints.extend([
                    cruisestate[varkey][i] == enginestate[varkey][i+Nclimb]
                    ])           
        
        return constraints

class Fuselage(Model):
    '''
    A double-bubble fuselage model
    '''

    def setup(self, **kwargs):
        g = Variable('g',9.81,'m*s^-2','Acceleration due to gravity')
        dPover = Variable('\\delta_P_{over}', 'psi', 'Cabin overpressure')
        npax = Variable('n_{pax}', '-', 'Number of Passengers to Carry')
        Nland = Variable('N_{land}', 6.0, '-',
                         'Emergency landing load factor')  # [TAS]
        SPR = Variable('SPR', '-', 'Number of seats per row')
        nrows = Variable('n_{rows}', '-', 'Number of rows')
        nseat = Variable('n_{seat}', '-', 'Number of seats')
        pitch = Variable('p_s', 'cm', 'Seat pitch')

        # Cross-sectional variables
        Adb = Variable('A_{db}', 'm^2', 'Web cross sectional area')
        Afloor = Variable('A_{floor}', 'm^2', 'Floor beam x-sectional area')
        Afuse = Variable('A_{fuse}', 'm^2', 'Fuselage x-sectional area')
        Askin = Variable('A_{skin}', 'm^2', 'Skin cross sectional area')
        hdb = Variable('h_{db}', 'm', 'Web half-height')
        hfloor = Variable('h_{floor}', 'm', 'Floor beam height')
        hfuse = Variable('h_{fuse}', 'm', 'Fuselage height')
        # will assume for now there: no under-fuselage extension deltaR
        Rfuse = Variable('R_{fuse}', 'm', 'Fuselage radius')
        tdb = Variable('t_{db}', 'm', 'Web thickness')
        thetadb = Variable('\\theta_{db}', '-', 'DB fuselage joining angle')
        tshell = Variable('t_{shell}', 'm', 'Shell thickness')
        tskin = Variable('t_{skin}', 'm', 'Skin thickness')
        waisle = Variable('w_{aisle}', 'm', 'Aisle width')
        wdb = Variable('w_{db}', 'm', 'DB added half-width')
        wfloor = Variable('w_{floor}', 'm', 'Floor half-width')
        wfuse = Variable('w_{fuse}', 'm', 'Fuselage width')
        wseat = Variable('w_{seat}', 'm', 'Seat width')
        wsys = Variable('w_{sys}', 'm', 'Width between cabin and skin for systems')

        # Tail cone variables
        lamcone = Variable('\\lambda_{cone}', '-', 'Tailcone radius taper ratio')
        lcone = Variable('l_{cone}', 'm', 'Cone length')
        plamv = Variable('p_{\\lambda_v}', 1.5, '-', '1 + 2*Tail taper ratio')
        # tcone = Variable('t_{cone}', 'm', 'Cone thickness') # perhaps to be added later

        # Lengths
        c0 = Variable('c_0', 'm', 'Root chord of the wing')
        lfuse = Variable('l_{fuse}', 'm', 'Fuselage length')
        lnose = Variable('l_{nose}', 'm', 'Nose length')
        lshell = Variable('l_{shell}', 'm', 'Shell length')
        lfloor = Variable('l_{floor}', 'm', 'Floor length')

        # Surface areas
        Sbulk = Variable('S_{bulk}', 'm^2', 'Bulkhead surface area')
        Snose = Variable('S_{nose}', 'm^2', 'Nose surface area')

        # Volumes
        Vbulk = Variable('V_{bulk}', 'm^3', 'Bulkhead skin volume')
        Vcabin = Variable('V_{cabin}', 'm^3', 'Cabin volume')
        Vcone = Variable('V_{cone}', 'm^3', 'Cone skin volume')
        Vcyl = Variable('V_{cyl}', 'm^3', 'Cylinder skin volume')
        Vdb = Variable('V_{db}', 'm^3', 'Web volume')
        Vfloor = Variable('V_{floor}', 'm^3', 'Floor volume')
        Vnose = Variable('V_{nose}', 'm^3', 'Nose skin volume')

        # Loads
        sigskin = Variable('\\sigma_{skin}', 'N/m^2', 'Max allowable skin stress')
        sigth = Variable('\\sigma_{\\theta}', 'N/m^2', 'Skin hoop stress')
        sigx = Variable('\\sigma_x', 'N/m^2', 'Axial stress in skin')

        # Floor loads
        Mfloor = Variable('M_{floor}', 'N*m',
                          'Max bending moment in floor beams')
        Pfloor = Variable('P_{floor}', 'N', 'Distributed floor load')
        Sfloor = Variable('S_{floor}', 'N', 'Maximum shear in floor beams')
        sigfloor = Variable('\\sigma_{floor}', 'N/m^2', 'Max allowable floor stress')
        taucone = Variable('\\tau_{cone}', 'N/m^2', 'Shear stress in cone')
        taufloor = Variable('\\tau_{floor}', 'N/m^2', 'Max allowable shear web stress')

        # Bending inertias (ported from TASOPT)
        # (shell inertia contribution)
        A0h = Variable('A0h', 'm^2', 'Horizontal bending area constant A0h')
        # (tail impact + aero loading)
        A1h = Variable('A1h', 'm', 'Horizontal bending area constant A1h')
        # (fuselage impact)
        A2h = Variable('A2h', '-', 'Horizontal bending area constant A2h')
        Ahbendb = Variable('A_{hbendb}', 'm^2',
                           'Horizontal bending area at rear wingbox')
        Ahbendf = Variable('A_{hbendf}', 'm^2',
                           'Horizontal bending area at front wingbox')
        # Avbendb = Variable('A_{vbendb}', 'm^2',
        #                    'Vertical bending material area at rear wingbox')
        # B0           = Variable('B0','m^2','Vertical bending area constant B0') #(shell inertia contribution)
        # B1           = Variable('B1','m','Vertical bending area constant B1')
        # #(vertical tail bending load)
        Ihshell = Variable('I_{hshell}', 'm^4',
                           'Shell horizontal bending inertia')
        #Ivshell      = Variable('I_{vshell}','m^4','Shell vertical bending inertia')
        rMh = Variable('r_{M_h}', .4, '-','Horizontal inertial relief factor')  # [TAS]
        rMv = Variable('r_{M_v}', .7, '-','Vertical inertial relief factor')  # [TAS]
        sigbend = Variable('\\sigma_{bend}', 'N/m^2',
                           'Bending material stress')
        sigMh = Variable('\\sigma_{M_h}', 'N/m^2',
                         'Horizontal bending material stress')
        #sigMv        = Variable('\\sigma_{M_v}','N/m^2','Vertical bending material stress')
        Vhbend = Variable('V_{hbend}', 'm^3',
                          'Horizontal bending material volume')
        Vhbendb = Variable(
            'V_{hbendb}', 'm^3', 'Horizontal bending material volume b')  # back fuselage
        Vhbendc = Variable('V_{hbendc}', 'm^3',
                           'Horizontal bending material volume c') # center fuselage
        Vhbendf = Variable('V_{hbendf}', 'm^3',
                           'Horizontal bending material volume f') # front fuselage
        #Vvbend       = Variable('V_{vbend}','m^3','Vertical bending material volume')
        # Vvbendb      = Variable('V_{vbendb}','m^3','Vertical bending material volume b') #back fuselage
        # Vvbendc      = Variable('V_{vbendc}','m^3','Vertical bending material
        # volume c') #center fuselage
        Whbend = Variable('W_{hbend}', 'lbf',
                          'Horizontal bending material weight')
        #Wvbend       = Variable('W_{vbend}','N','Vertical bending material weight')
        xhbend = Variable('x_{hbend}', 'm', 'Horizontal zero bending location')
        #xvbend       = Variable('x_{vbend}','m','Vertical zero bending location')

        # Material properties
        rE = Variable('r_E', 1., '-', 'Ratio of stringer/skin moduli')  # [TAS] # [b757 freight doc]
        rhocargo = Variable('\\rho_{cargo}', 150, 'kg/m^3', 'Cargo density')
        rhocone = Variable('\\rho_{cone}', 'kg/m^3',
                           'Cone material density')  # [TAS]
        rhobend = Variable('\\rho_{bend}', 'kg/m^3',
                           'Stringer density')  # [TAS]
        rhofloor = Variable('\\rho_{floor}', 'kg/m^3',
                            'Floor material density')  # [TAS]
        rholugg = Variable('\\rho_{lugg}', 100,
                           'kg/m^3', 'Luggage density')  # [Philippe]
        rhoskin = Variable('\\rho_{skin}', 'kg/m^3', 'Skin density')  # [TAS]
        Wppfloor = Variable('W\'\'_{floor}', 'N/m^2',
                            'Floor weight/area density')  # [TAS]
        Wppinsul = Variable(
            'W\'\'_{insul}', 'N/m^2', 'Weight/area density of insulation material')  # [TAS]
        Wpseat = Variable('W\'_{seat}', 'N', 'Weight per seat')  # [TAS]
        Wpwindow = Variable('W\'_{window}', 'N/m',
                            'Weight/length density of windows')  # [TAS]

        # Weight fractions
        fapu = Variable('f_{apu}', 0.035, '-',
                        'APU weight as fraction of payload weight')  # [TAS]
        ffadd = Variable(
            'f_{fadd}', '-', 'Fractional added weight of local reinforcements')  # [TAS]
        fframe = Variable('f_{frame}', '-',
                          'Fractional frame weight')  # [Philippe]
        flugg1 = Variable(
            'f_{lugg,1}', '-', 'Proportion of passengers with one suitcase')  # [Philippe]
        flugg2 = Variable(
            'f_{lugg,2}', '-', 'Proportion of passengers with two suitcases')  # [Philippe]
        fpadd = Variable('f_{padd}', 0.4, '-',
                         'Other misc weight as fraction of payload weight')
        fstring = Variable('f_{string}', '-',
                           'Fractional stringer weight')  # [Philippe]

        # Weights
        Wapu = Variable('W_{apu}', 'lbf', 'APU weight')
        Wavgpass = Variable('W_{avg. pass}', 'lbf',
                            'Average passenger weight')  # [Philippe]
        Wcargo = Variable('W_{cargo}', 'N', 'Cargo weight')  # [Philippe]
        Wcarryon = Variable('W_{carry on}', 'lbf',
                            'Ave. carry-on weight')  # [Philippe]
        Wchecked = Variable('W_{checked}', 'lbf',
                            'Ave. checked bag weight')  # [Philippe]
        Wcone = Variable('W_{cone}', 'lbf', 'Cone weight')
        Wdb = Variable('W_{db}', 'lbf', 'Web weight')
        Wfix = Variable(
            'W_{fix}', 'lbf', 'Fixed weights (pilots, cockpit seats, navcom)')
        Wfloor = Variable('W_{floor}', 'lbf', 'Floor weight')
        Wfuse = Variable('W_{fuse}', 'lbf', 'Fuselage weight')
        Winsul = Variable('W_{insul}', 'lbf', 'Insulation material weight')
        Wlugg = Variable('W_{lugg}', 'lbf', 'Passenger luggage weight')
        Wpadd = Variable('W_{padd}', 'lbf',
                         'Misc weights (galley, toilets, doors etc.)')
        Wpax = Variable('W_{pax}', 'lbf', 'Passenger weight')
        Wpay = Variable('W_{payload}', 'lbf', 'Payload weight')
        Wseat = Variable('W_{seat}', 'lbf', 'Seating weight')
        Wshell = Variable('W_{shell}', 'lbf', 'Shell weight')
        Wskin = Variable('W_{skin}', 'lbf', 'Skin weight')
        Wtail = Variable('W_{tail}', 'lbf', 'Total tail weight')
        Wwindow = Variable('W_{window}', 'lbf', 'Window weight')

        # x-location variables
        xshell1 = Variable('x_{shell1}', 'm', 'Start of cylinder section')
        xshell2 = Variable('x_{shell2}', 'm', 'End of cylinder section')
        xtail = Variable('x_{tail}', 'm', 'x-location of tail')
        xwing = Variable('x_{wing}', 'm', 'x-location of wing')

        # Wingbox variables
        xf = Variable('x_f', 'm', 'x-location of front of wingbox')
        xb = Variable('x_b', 'm', 'x-location of back of wingbox')
        w = Variable('wtc', 0.5, '-', 'Wingbox-width-to-chord ratio')

        constraints = []
        with SignomialsEnabled():
            constraints.extend([

                # Passenger constraints
                Wlugg >= flugg2 * npax * 2 * Wchecked + flugg1 * npax * Wchecked + Wcarryon,
                Wpax == npax * Wavgpass,
                Wpay >= Wpax + Wlugg + Wcargo,
                nseat == npax,
                nrows == nseat / SPR,
                lshell == nrows * pitch,

                # Fuselage joint angle relations
                thetadb == wdb / Rfuse,  # first order Taylor works...
                hdb >= Rfuse * (1.0 - .5 * thetadb**2),  # [SP]

                # Cross-sectional constraints
                Adb == (2 * hdb) * tdb,
                Afuse >= (pi + 2 * thetadb + 2 * thetadb * \
                          (1 - thetadb**2 / 2)) * Rfuse**2,  # [SP]
                # Afuse       >= (pi + 4*thetadb)*Rfuse**2, #Bad approx, should
                # improve
                Askin >= (2 * pi + 4 * thetadb) * Rfuse * \
                tskin + Adb,  # no delta R for now
                wfloor == .5 * wfuse,
                TCS([wfuse >= SPR * wseat + 2 * waisle + 2 * wsys + tdb]),
                wfuse <= 2 * (Rfuse + wdb),
                hfuse == Rfuse,
                TCS([tshell <= tskin * (1. + rE * fstring * rhoskin / rhobend)]), #[SP]

                # Fuselage surface area relations
                Snose >= (2 * pi + 4 * thetadb) * Rfuse**2 * \
                (1 / 3 + 2 / 3 * (lnose / Rfuse)**(8 / 5))**(5 / 8),
                Sbulk >= (2 * pi + 4 * thetadb) * Rfuse**2,

                # Fuselage length relations
                SignomialEquality(lfuse, lnose + lshell + lcone),  
                lnose == 0.3 * lshell,  # TODO remove
                lcone == Rfuse / lamcone,
                xshell1 == lnose,
                TCS([xshell2 >= lnose + lshell]), 
                # STRESS RELATIONS
                # Pressure shell loading
                tskin == dPover * Rfuse / sigskin,
                tdb == 2 * dPover * wdb / sigskin,
                sigx == dPover * Rfuse / (2 * tshell),
                sigth == dPover * Rfuse / tskin,

                # Floor loading
                lfloor >= lshell + 2 * Rfuse,
                Pfloor >= Nland * (Wpay + Wseat),
                Mfloor == 9. / 256. * Pfloor * wfloor,
                Afloor >= 2. * Mfloor / (sigfloor * hfloor) + 1.5 * Sfloor / taufloor,
                Vfloor == 2 * wfloor * Afloor,
                Wfloor >= rhofloor * g * Vfloor + 2 * wfloor * lfloor * Wppfloor,
                Sfloor == (5. / 16.) * Pfloor,
                hfloor <= 0.1 * Rfuse,

                # Tail cone sizing
                taucone == sigskin,
                Wcone >= rhocone * g * Vcone * (1 + fstring + fframe),
                SignomialEquality(xtail, lnose + lshell + .5 * lcone),  #[SP] #[SPEquality]
                
                # Horizontal bending model
                # Maximum axial stress is the sum of bending and pressurization
                # stresses
                Ihshell <= ((pi + 4 * thetadb) * Rfuse**2) * \
                Rfuse * tshell + 2 / 3 * hdb**3 * tdb,  # [SP]
                # Ivshell <= (pi*Rfuse**2 + 8*wdb*Rfuse +
                # (2*pi+4*thetadb)*wdb**2)*Rfuse*tshell, #[SP] #Ivshell
                # approximation needs to be improved
                sigbend == rE * sigskin,

                # Horizontal bending material model
                # Calculating xbend, the location where additional bending
                # material is required
                xhbend >= xwing,
                # [SP] #[SPEquality]
                SignomialEquality(A0h, A2h * (xshell2 - xhbend) ** 2 + A1h * (xtail - xhbend)),
                A2h >= Nland * (Wpay + Wshell + Wwindow + Winsul + Wfloor + Wseat) / \
                (2 * lshell * hfuse * sigMh),  # Landing loads constant A2h
                # Shell inertia constant A0h
                A0h == (Ihshell / (rE * hfuse**2)), # [SP]  # Bending area forward of wingbox
                Ahbendf >= A2h * (xshell2 - xf)**2 + A1h * (xtail - xf) - A0h, # [SP]  # Bending area behind wingbox
                Ahbendb >= A2h * (xshell2 - xb)**2 + A1h * (xtail - xb) - A0h, # [SP]
                Vhbendf >= A2h / 3 * ((xshell2 - xf)**3 - (xshell2 - xhbend)**3) \
                + A1h / 2 * ((xtail - xf)**2 - (xtail - xhbend)**2) \
                + A0h * (xhbend - xf),  # [SP] # Bending volume forward of wingbox
                Vhbendb >= A2h / 3 * ((xshell2 - xb)**3 - (xshell2 - xhbend)**3) \
                + A1h / 2 * ((xtail - xb)**2 - (xtail - xhbend)**2) \
                + A0h * (xhbend - xb),  # [SP] # Bending volume behind wingbox
                Vhbendc >= .5 * (Ahbendf + Ahbendb) * c0 * w, # Bending volume over wingbox
                Vhbend >= Vhbendc + Vhbendf + Vhbendb,
                Whbend >= g * rhobend * Vhbend,

                # Wing variable substitutions
                SignomialEquality(xf, xwing + .5 * c0 * w),  # [SP] [SPEquality]
                SignomialEquality(xb, xwing - .5 * c0 * w),  # [SP] [SPEquality]

                sigMh <= sigbend - rE * dPover / 2 * Rfuse / tshell,

                # Volume relations
                Vcyl == Askin * lshell,
                Vnose == Snose * tskin,
                Vbulk == Sbulk * tskin,
                Vdb == Adb * lshell,
                # TODO Revert to posynomial after debugging
                # [SP] #[SPEquality]
                SignomialEquality(Vcabin, Afuse * (lshell + 0.67 * lnose + 0.67 * Rfuse)),

                # Weight relations
                Wapu == Wpay * fapu,
                Wdb == rhoskin * g * Vdb,
                Winsul >= Wppinsul * ((1.1 * pi + 2 * thetadb) * Rfuse * lshell + 0.55 * (Snose + Sbulk)),
                Wlugg >= flugg2 * npax * 2 * Wchecked + flugg1 * npax * Wchecked + Wcarryon,
                Wwindow >= Wpwindow * lshell,
                Wpadd == Wpay * fpadd,
                Wseat == Wpseat * nseat,

                Wskin >= rhoskin * g * (Vcyl + Vnose + Vbulk),
                Wshell >= Wskin * (1 + fstring + ffadd + fframe) + Wdb,
                Wfuse >= Wshell + Wfloor + Wtail + Winsul + \
                    Wapu + Wfix + Wwindow + Wpadd + Wseat + Whbend,
            ])

        return constraints

    def dynamic(self, state):
        """
        returns a fuselage performance model
        """
        return FuselagePerformance(self, state)


class FuselagePerformance(Model):
    """
    Fuselage performance model
    """

    def setup(self, fuse, state, **kwargs):
        # new variables
        Cdfuse = Variable('C_{D_{fuse}}', '-', 'Fuselage Drag Coefficient')
        Dfuse = Variable('D_{fuse}', 'N', 'Total drag in cruise')
        Dfrict = Variable('D_{friction}', 'N', 'Friction drag')
        Dupswp = Variable('D_{upsweep}', 'N', 'Drag due to fuse upsweep')
        f = Variable('f', '-', 'Fineness ratio')
        FF = Variable('FF', '-', 'Fuselage form factor')
        phi = Variable('\\phi', '-', 'Upsweep angle')

        constraints = []
        constraints.extend([
            #Dfuse == Cdfuse * (.5 * fuse['A_{fuse}'] * state.atm['\\rho'] * state['V']**2),
            # fineness ratio
            f == fuse['l_{fuse}'] / ((4 / np.pi * fuse['A_{fuse}'])**0.5),
            FF >= 1 + 60 / f**3 + f / 400,  # form factor
            Dfrict >= FF * np.pi * fuse['R_{fuse}'] * state.atm['\\mu'] * state['V'] * 0.074 * (state.atm['\\rho'] * state['V']
                                                                                                * fuse['l_{fuse}'] / state.atm['\\mu'])**0.8,
            # Monomial fit of tan(phi)
            1.13226 * phi**1.03759 == fuse['R_{fuse}'] / fuse['l_{cone}'],
            Dupswp >= 3.83 * phi**2.5 * fuse['A_{fuse}'] * 0.5 * state.atm['\\rho'] * state['V']**2,
            Dfuse >= Dfrict + Dupswp,
            Dfuse == 0.5 * state.atm['\\rho'] * state['V']**2 * Cdfuse * fuse['A_{fuse}'],
        ])

        return constraints


class Mission(Model):
    """
    Mission superclass, links together all subclasses into an optimization problem
    """

    def setup(self, **kwargs):
        # define the number of each flight segment
        Nclimb = 2
        Ncruise = 2

        # vectorize
        with Vectorize(Nclimb + Ncruise):
            enginestate = FlightState()

        # build required submodels
        aircraft = Aircraft(Nclimb, Ncruise, enginestate)

        # vectorize
        with Vectorize(Nclimb):
            climb = ClimbSegment(aircraft, Nclimb)

        with Vectorize(Ncruise):
            cruise = CruiseSegment(aircraft, Nclimb)

        statelinking = StateLinking(climb.state, cruise.state, enginestate, Nclimb, Ncruise)

        # declare new variables
        W_ftotal = Variable('W_{f_{total}}', 'lbf', 'Total Fuel Weight')
        W_fclimb = Variable('W_{f_{climb}}', 'lbf',
                            'Fuel Weight Burned in Climb')
        W_fcruise = Variable('W_{f_{cruise}}', 'lbf',
                             'Fuel Weight Burned in Cruise')
        W_total = Variable('W_{total}', 'lbf', 'Total Aircraft Weight')
        W_dry = Variable('W_{dry}', 'lbf', 'Dry Aircraft Weight')
        CruiseAlt = Variable('CruiseAlt', 'ft', 'Cruise Altitude [feet]')
        ReqRng = Variable('ReqRng', 'nautical_miles', 'Required Cruise Range')

        h = climb.state['h']
        hftClimb = climb.state['hft']
        dhft = climb.climbP['dhft']
        hftCruise = cruise.state['hft']

        # make overall constraints
        constraints = []
        with SignomialsEnabled():
            constraints.extend([
            # Total takeoff weight constraint
            TCS([aircraft['W_{fuse}'] + aircraft['W_{payload}'] + W_ftotal + aircraft['numeng']
                 * aircraft.engine['W_{engine}'] + aircraft.wing.wb['W_{struct}'] <= W_total]),


            climb.climbP.aircraftP['W_{start}'][0] == W_total,
            climb.climbP.aircraftP[
                'W_{end}'][-1] == cruise.cruiseP.aircraftP['W_{start}'][0],

            # similar constraint 1
            TCS([climb.climbP.aircraftP['W_{start}'] >= climb.climbP.aircraftP[
                'W_{end}'] + climb.climbP.aircraftP['W_{burn}']]),
            # similar constraint 2
            TCS([cruise.cruiseP.aircraftP['W_{start}'] >= cruise.cruiseP.aircraftP[
                'W_{end}'] + cruise.cruiseP.aircraftP['W_{burn}']]),

            climb.climbP.aircraftP['W_{start}'][
                1:] == climb.climbP.aircraftP['W_{end}'][:-1],
            cruise.cruiseP.aircraftP['W_{start}'][
                1:] == cruise.cruiseP.aircraftP['W_{end}'][:-1],

            TCS([aircraft['W_{fuse}'] + aircraft['W_{payload}'] + aircraft['numeng'] * aircraft.engine['W_{engine}'] + \
                 aircraft.wing.wb['W_{struct}'] <= cruise.cruiseP.aircraftP['W_{end}'][-1]]),

            TCS([W_ftotal >= W_fclimb + W_fcruise]),
            TCS([W_fclimb >= sum(climb.climbP['W_{burn}'])]),
            TCS([W_fcruise >= sum(cruise.cruiseP['W_{burn}'])]),

            # Altitude constraints
            hftCruise == CruiseAlt,
            TCS([hftClimb[1:Ncruise] >= hftClimb[:Ncruise - 1] + dhft]),
            TCS([hftClimb[0] >= dhft[0]]),
            hftClimb[-1] <= hftCruise,

            # Compute dh
            dhft == hftCruise / Nclimb,

            # Thrust constraint
            aircraft.VT['T_e'] == aircraft.engine['F'][0],

            # Set the range for each cruise segment; take credit for
            # down range distance covered during climb
            TCS([cruise.cruiseP['Rng'] >= 0.8*ReqRng/(Ncruise)]),
            cruise.cruiseP['Rng'][0] == cruise.cruiseP['Rng'][1],
            ReqRng <= sum(cruise.cruiseP['Rng']) + sum(climb.climbP['RngClimb']), #[SP]

            # Wing fuel constraints
            aircraft.wing['W_{fuel_{wing}}'] == W_ftotal,

            aircraft.engine['F_{spec}'][0] == 63.*units('kN'), #94.971 * units('kN'), #63.184 * units('kN'),
            aircraft.engine['F_{spec}'][1] == 45.*units('kN'), #63.184 * units('kN'), #40 * units('kN'),
##          aircraft.engine['F_{spec}'][2] == 30.109* units('kN'),
##          aircraft.engine['F_{spec}'][3] == 22.182 * units('kN'),

            SignomialEquality(W_dry, aircraft['W_{fuse}'] + aircraft['numeng'] * aircraft.engine['W_{engine}'] + \
                aircraft.wing.wb['W_{struct}']),
            ])

        M2 = .8
        M0 = .8
        M25 = .6
        M4a = .1025
        
        engineclimb = [
            aircraft.engine.engineP['M_2'][0] == climb['M'][0],
            aircraft.engine.engineP['M_2'][1] == climb['M'][1],
            aircraft.engine.engineP['M_{2.5}'][0] == M25,
            aircraft.engine.engineP['M_{2.5}'][1] == M25,
            aircraft.engine.compressor['hold_{2}'] == 1+.5*(1.398-1)*M2**2,
            aircraft.engine.compressor['hold_{2.5}'] == 1+.5*(1.354-1)*M25**2,
            aircraft.engine.compressor['c1'] == 1+.5*(.401)*M0**2,
            ]


        M25 = .6
        M4a = .1025

        enginecruise = [
            aircraft.engine.engineP['M_2'][2] == cruise['M'][0],
            aircraft.engine.engineP['M_2'][3] == cruise['M'][1],

##            cruise['M'] == .8,

            aircraft.engine.engineP['M_{2.5}'][2] == M25,
            aircraft.engine.engineP['M_{2.5}'][3] == M25,
            ]

        self.cost = W_ftotal * units('1/N') + (aircraft.engine['TSFC'][2]+aircraft.engine['TSFC'][1]+aircraft.engine['TSFC'][0]+aircraft.engine['TSFC'][3])*units('hr') * ((aircraft.engine['W_{engine}'] * units('1/N'))**.00001)

        return constraints, aircraft, climb, cruise, statelinking, enginestate, enginecruise, engineclimb

if __name__ == '__main__':
    M4a = .1025
    fan = 1.685
    lpc  = 4.744
    hpc = 3.75
    substitutions = {
            # 'V_{stall}'   : 120,
            '\\delta_P_{over}': 12*units('psi'),
            'N_{land}': 6,
            'SPR': 8,
            'p_s': 81.*units('cm'),
            'ReqRng': 1000*units('nmi'),
            '\\theta_{db}' : 0.366,
            'CruiseAlt': 30000*units('ft'),
            'numeng': 2,
            'n_{pax}': 150,
            'W_{avg. pass}': 180*units('lbf'),
            'W_{carry on}': 15*units('lbf'),
            'W_{cargo}': 10000*units('N'),
            'W_{checked}': 40*units('lbf'),
            'W_{fix}': 3000*units('lbf'),
            'w_{aisle}': 0.51*units('m'),
            'w_{seat}': 0.5*units('m'),
            'w_{sys}': 0.1*units('m'),
            'r_E': 1,  # [TAS]
            '\\lambda_{cone}': 0.4,  # [Philippe]
            '\\rho_{cone}': 2700,#*units('kg/m^3'),  # [TAS]
            '\\rho_{bend}': 2700,#*units('kg/m^3'),  # [TAS]
            '\\rho_{floor}': 2700,#*units('kg/m^3'),  # [TAS]
            '\\rho_{skin}': 2700,#*units('kg/m^3'),  # [TAS]
            '\\sigma_{floor}': 30000 / 0.000145, # [TAS] [Al]
            '\\sigma_{skin}': 15000 / 0.000145,  # [TAS] [Al]
            '\\tau_{floor}': 30000 / 0.000145, # [TAS] [Al]
            'W\'\'_{floor}': 60,  # [TAS]
            'W\'\'_{insul}': 22,  # [TAS]
            'W\'_{seat}': 150,  # [TAS]
            'W\'_{window}': 145. * 3,  # [TAS]

            # Fractional weights
            'f_{fadd}': 0.2,  # [TAS]
            'f_{frame}': 0.25,  # [Philippe]
            'f_{lugg,1}': 0.4,  # [Philippe]
            'f_{lugg,2}': 0.1,  # [Philippe]
            'f_{padd}': 0.4,  # [TAS]

            # Wing substitutions
            'C_{L_{wmax}}': 2.5,
            '\\tan(\\Lambda)': tan(sweep * pi / 180),
            '\\alpha_{max,w}': 0.1,  # (6 deg)
            '\\cos(\\Lambda)': cos(sweep * pi / 180),
            '\\eta': 0.97,
            '\\rho_0': 1.225*units('kg/m^3'),
            '\\rho_{fuel}': 817*units('kg/m^3'),  # Kerosene [TASOPT]

            # VT substitutions
           'C_{D_{wm}}': 0.5, # [2]
           'C_{L_{vmax}}': 2.6, # [2]
           'V_1': 70*units('m/s'),
           '\\rho_{TO}': 1.225*units('kg/m^3'),
            '\\tan(\\Lambda_{vt})': np.tan(40*np.pi/180),
            'c_{l_{vtEO}}': 0.5,
            'e_v': 0.8,
            # 'y_{eng}': 4.83*units('m'), # [3]
            'V_{land}': 72*units('m/s'),
            'I_{z}': 12495000, # estimate for late model 737 at max takeoff weight (m l^2/12)
            '\\dot{r}_{req}': 0.174533, # 10 deg/s yaw rate
            'N_{spar}': 2,

            # HT substitutions
            '\\alpha_{max,h}': 2.5,
            '\\tan(\\Lambda_{ht})': tan(30*pi/180),
            'C_{L_{hmax}}': 2.5,
            'SM_{min}': 0.05,
            '\\Delta x_{CG}': 2.0*units('m'),
            'x_{CG_{min}}' : 13.0*units('m'),

            # Engine substitutions
    ##        'W_{engine}': 40000, # Engine weight substitution
    ##        'A_2': np.pi*(.5*1.75)**2, # Engine inlet area substitution

            # Cabin air substitutions in AircraftP

                #engine subs
                '\\pi_{tn}': .989,
                '\pi_{b}': .94,
                '\pi_{d}': .998,
                '\pi_{fn}': .98,
                'T_{ref}': 288.15,
                'P_{ref}': 101.325,
                '\eta_{HPshaft}': .97,
                '\eta_{LPshaft}': .97,
                'eta_{B}': .9827,

                '\pi_{f_D}': fan,
                '\pi_{hc_D}': hpc,
                '\pi_{lc_D}': lpc,

                'hold_{4a}': 1+.5*(1.313-1)*M4a**2,#sol('hold_{4a}'),
                'r_{uc}': .5,
                '\\alpha_c': .19036,
                'T_{t_f}': 435,

                'M_{takeoff}': .972,

                'G_f': 1,

                'h_f': 43.003,

                'Cp_t1': 1280,
                'Cp_t2': 1184,
                'Cp_c': 1216,
    }
    sweeps = False
    if sweeps == False:
        m = Mission()
        m.substitutions.update(substitutions)
        # m = Model(m.cost,BCS(m))
        sol = m.localsolve( verbosity = 2, iteration_limit=50)

    if sweeps:
        if sweepSMmin:
            m = Mission()
            m.substitutions.update(substitutions)
            SMminArray = np.linspace(0.05,0.5,n)
            m.substitutions.update({'SM_{min}': ('sweep',SMminArray)})
            solSMsweep = m.localsolve(verbosity = 2, skipsweepfailures=True)

            if plot:
                plt.plot(solSMsweep('SM_{min}'), solSMsweep('S_h'), '-r')
                plt.xlabel('Minimum Allowed Static Margin')
                plt.ylabel('Horizontal Tail Area [m$^2$]')
                plt.title('Horizontal Tail Area vs Min Static Margin')
                plt.savefig('CFP_Sweeps/S_{h}-vs-SM_{min}.pdf')
                plt.show(), plt.close()

                plt.plot(solSMsweep('SM_{min}'), solSMsweep('V_{h}'), '-r')
                plt.xlabel('Minimum Allowed Static Margin')
                plt.ylabel('Horizontal Tail Volume Coefficient')
                plt.title('Horizontal Tail Volume Coefficient vs Min Static Margin')
                plt.savefig('CFP_Sweeps/V_{h}-vs-SM_{min}.pdf')
                plt.show(), plt.close()

                plt.plot(solSMsweep('SM_{min}'), np.mean(solSMsweep('x_{CG}_Mission, CruiseSegment, CruiseP, AircraftP'),axis = 1), '-r')
                plt.xlabel('Minimum Allowed Static Margin')
                plt.ylabel('CG Location [m]')
                plt.title('CG Location vs Min Static Margin')
                plt.savefig('CFP_Sweeps/x_{CG}-vs-SM_{min}.pdf')
                plt.show(), plt.close()

        if sweepReqRng:
            m = Mission()
            m.substitutions.update(substitutions)
            ReqRngArray = np.linspace(500,3000,n)
            m.substitutions.update({'ReqRng': ('sweep',ReqRngArray)})
            solReqRngsweep = m.localsolve(verbosity=2, iteration_limit=25, skipsweepfailures=True)

            if plot:
                plt.plot(solReqRngsweep('ReqRng'),solReqRngsweep('W_{f_{total}}'))
                plt.xlabel('Range [nmi]')
                plt.ylabel('Total Fuel Weight [lbf]')
                plt.title('Total Fuel Weight vs Range')
                plt.savefig('CFP_Sweeps/W_ftotal-vs-ReqRng.pdf')
                plt.show(), plt.close()

                plt.plot(solReqRngsweep('ReqRng'),solReqRngsweep('W_{dry}'))
                plt.xlabel('Range [nmi]')
                plt.ylabel('Dry Weight [lbf]')
                plt.title('Dry Weight vs Range')
                plt.savefig('CFP_Sweeps/W_dry-vs-ReqRng.pdf')
                plt.show(), plt.close()

                plt.plot(solReqRngsweep('ReqRng'),solReqRngsweep('S'))
                plt.xlabel('Range [nmi]')
                plt.ylabel('Wing Area [m^2]')
                plt.title('Wing Area vs Range')
                plt.savefig('CFP_Sweeps/S-vs-ReqRng.pdf')
                plt.show(), plt.close()

                plt.plot(solReqRngsweep('ReqRng'),solReqRngsweep('b'))
                plt.xlabel('Range [nmi]')
                plt.ylabel('Wing Span [m]')
                plt.title('Wing Span vs Range')
                plt.savefig('CFP_Sweeps/b-vs-ReqRng.pdf')
                plt.show(), plt.close()

        if sweepthetadb:
            m = Mission()
            m.substitutions.update(substitutions)
            thetadbArray = np.linspace(0,0.5,n)
            m.substitutions.update({'\\theta_{db}': ('sweep', thetadbArray)})
            solthetadbsweep = m.localsolve(verbosity=2, iteration_limit=25, skipsweepfailures=True)

            if plot:
                plt.plot(solthetadbsweep('\\theta_{db}'),solthetadbsweep('W_{f_{total}}'))
                plt.xlabel('Fuselage Joint Angle [radians]')
                plt.ylabel('Total Fuel Weight [lbf]')
                plt.title('Total Fuel Weight vs Fuselage Joint Angle')
                plt.savefig('CFP_Sweeps/W_ftotal-vs-thetadb.pdf')
                plt.show(), plt.close()

                plt.plot(solthetadbsweep('\\theta_{db}'),solthetadbsweep('W_{dry}'))
                plt.xlabel('Fuselage Joint Angle [radians]')
                plt.ylabel('Dry Weight [lbf]')
                plt.title('Dry Weight vs Fuselage Joint Angle')
                plt.savefig('CFP_Sweeps/W_dry-vs-thetadb.pdf')
                plt.show(), plt.close()

                plt.plot(solthetadbsweep('\\theta_{db}'),solthetadbsweep('W_{fuse}'))
                plt.xlabel('Fuselage Joint Angle [radians]')
                plt.ylabel('Fuselage Weight [lbf]')

                plt.title('Fuselage Weight vs Fuselage Joint Angle')
                plt.savefig('CFP_Sweeps/W_fuse-vs-thetadb.pdf')
                plt.show(), plt.close()



        if sweepdxCG:
            m = Mission()
            m.substitutions.update(substitutions)
            dxCGArray = np.linspace(0.5,3.5,n)
            m.substitutions.update({'\\Delta x_{CG}': ('sweep',dxCGArray)})
            soldxCGsweep = m.localsolve(verbosity=2,skipsweepfailures=True)

            if plot:
                plt.plot(soldxCGsweep('\\Delta x_{CG}'),soldxCGsweep('V_{h}'),'-r')
                plt.xlabel('Allowed CG shift [m]')
                plt.ylabel('Horizontal Tail Volume Coefficient')
                plt.title('Horizontal Tail Volume Coefficient vs Allowed CG Shift')
                plt.savefig('CFP_Sweeps/Vht-vs-dxCG.pdf')
                plt.show(), plt.close()

                plt.plot(soldxCGsweep('\\Delta x_{CG}'),np.mean(soldxCGsweep('x_{CG}_Mission, CruiseSegment, CruiseP, AircraftP'),axis = 1), '-r')
                plt.xlabel('Allowed CG shift [m]')
                plt.ylabel('Nominal CG location [m]')
                plt.title('CG Location vs Allowed CG Shift')
                plt.savefig('CFP_Sweeps/xCG-vs-dxCG.pdf')

                plt.plot(soldxCGsweep('\\Delta x_{CG}'),np.mean(soldxCGsweep('x_{AC}_Mission, CruiseSegment, CruiseP, AircraftP'),axis = 1), '-r')
                plt.xlabel('Allowed CG shift [m]')
                plt.ylabel('Average AC location [m]')
                plt.title('AC Location vs Allowed CG Shift')
                plt.savefig('CFP_Sweeps/xAC-vs-dxCG.pdf')

        if sweepxCG:
            m = Mission()
            m.substitutions.update(substitutions)
            xCGArray = np.linspace(8,14,n)
            m.substitutions.update({'x_{CG_{min}}': ('sweep',xCGArray)})
            solxCGsweep = m.localsolve(verbosity=2,skipsweepfailures=True,iteration_limit=30)

            if plot:
                plt.plot(solxCGsweep('x_{CG_{min}}'),solxCGsweep('V_{h}'),'-r')
                plt.xlabel('Max Forward CG [m]')
                plt.ylabel('Horizontal Tail Volume Coefficient')
                plt.title('Horizontal Tail Volume Coefficient vs Max Forward CG')
                plt.savefig('CFP_Sweeps/Vht-vs-xCG.pdf')
                plt.show(), plt.close()

                plt.plot(solxCGsweep('x_{CG_{min}}'),np.mean(solxCGsweep('x_{CG}_Mission, CruiseSegment, CruiseP, AircraftP'),axis = 1), '-r')
                plt.xlabel('Max Forward CG [m]')
                plt.ylabel('Nominal CG location [m]')
                plt.title('CG Location vs Max Forward CG')
                plt.savefig('CFP_Sweeps/xCG-vs-xCG.pdf')
                plt.show(), plt.close()

                plt.plot(solxCGsweep('x_{CG_{min}}'),np.mean(solxCGsweep('x_{AC}_Mission, CruiseSegment, CruiseP, AircraftP'),axis = 1), '-r')
                plt.xlabel('Max Forward CG [m]')
                plt.ylabel('Average AC location [m]')
                plt.title('AC Location vs Max Forward CG')
                plt.savefig('CFP_Sweeps/xAC-vs-xCG.pdf')
                plt.show(), plt.close()

        if sweepCruiseAlt:
            m = Mission()
            m.substitutions.update(substitutions)
            CruiseAltArray = np.linspace(25000,40000,n)
            m.substitutions.update({'CruiseAlt': ('sweep',CruiseAltArray)})
            solCruiseAltsweep = m.localsolve(verbosity=2,skipsweepfailures=True,iteration_limit=30)

            if plot:
                plt.plot(solCruiseAltsweep('CruiseAlt'),solCruiseAltsweep('W_{f_{total}}'))
                plt.xlabel('Cruise Altitude [ft]')
                plt.ylabel('Mission Fuel Burn [lbs]')
                plt.title('Fuel Burn vs Cruise Altitude')
                plt.savefig('CFP_Sweeps/Wftotal-vs-CruiseAlt.pdf')
                plt.show(), plt.close()

                plt.plot(solCruiseAltsweep('CruiseAlt'),solCruiseAltsweep('AR'))
                plt.xlabel('Cruise Altitude [ft]')
                plt.ylabel('Aspect Ratio')
                plt.title('Aspect Ratio vs Cruise Altitude')
                plt.savefig('CFP_Sweeps/AR-vs-CruiseAlt.pdf')
                plt.show(), plt.close()

                plt.plot(solCruiseAltsweep('CruiseAlt'),solCruiseAltsweep('S'))
                plt.xlabel('Cruise Altitude [ft]')
                plt.ylabel('Wing Area [ft^2]')
                plt.title('Wing Area vs Cruise Altitude')
                plt.savefig('CFP_Sweeps/S-vs-CruiseAlt.pdf')
                plt.show(), plt.close()

                plt.plot(solCruiseAltsweep('CruiseAlt'),np.mean(solCruiseAltsweep('M_Mission, CruiseSegment, FlightState'),axis = 1))
                plt.xlabel('Cruise Altitude [m]')
                plt.ylabel('Mach Number')
                plt.title('Average Mach Number vs Cruise Altitude')
                plt.savefig('CFP_Sweeps/M-vs-CruiseAlt.pdf')
                plt.show(), plt.close()

        if sweepW_engine:
            m = Mission()
            m.substitutions.update(substitutions)
            W_engineArray = np.linspace(10000,30000,n) # Tiny engine to GE90 weight
            m.substitutions.update({'W_{engine}':('sweep',W_engineArray)})
            solW_enginesweep = m.localsolve(verbosity=2,skipsweepfailures=True,iteration_limit=30)
            if plot:
                plt.plot(solW_enginesweep('W_{engine}'),solW_enginesweep('W_{f_{total}}'))
                plt.xlabel('Engine Weight [N]')
                plt.ylabel('Mission Fuel Burn [lbs]')
                plt.title('Fuel Burn vs Engine Weight')
                plt.savefig('CFP_Sweeps/Wftotal-vs-W_engine.pdf')
                plt.show(), plt.close()

                plt.plot(solW_enginesweep('W_{engine}'),solW_enginesweep('W_{tail}'))
                plt.xlabel('Engine Weight [N]')
                plt.ylabel('Tail Weight [lbs]')
                plt.title('Tail Weight vs Engine Weight')
                plt.savefig('CFP_Sweeps/Wtail-vs-W_engine.pdf')
                plt.show(), plt.close()

                plt.plot(solW_enginesweep('W_{engine}'),solW_enginesweep('W_{hbend}'))
                plt.xlabel('Engine Weight [N]')
                plt.ylabel('Fuselage Bending Reinforcement Weight [lbs]')
                plt.title('Fuselage Bending Reinforcement Weight vs Engine Weight')
                plt.savefig('CFP_Sweeps/Whbend-vs-W_engine.pdf')
                plt.show(), plt.close()

                plt.plot(solW_enginesweep('W_{engine}'),solW_enginesweep('f_{string}'))
                plt.xlabel('Engine Weight [N]')
                plt.ylabel('Stringer Mass Fraction')
                plt.title('Stringer Mass Fraction vs Engine Weight')
                plt.savefig('CFP_Sweeps/fstring-vs-W_engine.pdf')
                plt.show(), plt.close()

        if sweepCruiseMach:
            m = Mission()
            m.substitutions.update(substitutions)
            CruiseMachArray
    # template
    #             plt.plot()
    #             plt.xlabel()
    #             plt.ylabel()
    #             plt.title()
    #             plt.savefig('CFP_Sweeps/')

