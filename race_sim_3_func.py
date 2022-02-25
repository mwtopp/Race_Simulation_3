# import the required modules / functions
from datetime import timedelta
from scipy.integrate import quad
from scipy import optimize
import pandas as pd
import math as math
from matplotlib import pyplot as plt
import copy
import time

# create global variables
race_time = timedelta(seconds = 0)
positions_dict = {}
finished_cars = []
car_length = 0
debug = 0
car_position = 0
stuck_behind = False

class TimerError(Exception):
    """a custom exception used to report errors in the use of the Timer class"""
    
class Timer():
    """a custom timer object to monitor function / simulation performance"""
    
    def __init__(self):
        self._start_time = None
        self.elapsed_time = None
        
    def start(self):
        """Start a new Timer"""
        if self._start_time is not None:
            raise TimeError(f"Timer is running. Use .stop to stop it")
        
        self._start_time = time.perf_counter()
        
    def stop(self):
        """Stop the Timer"""
        if self._start_time is None:
            raise TimeError(f"Timer is not running. Use .start to start it")
            
        self.elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None

class Car:
    
    """simulates a race car
    
        parameters
        ----------
        name: str
            instance name
        max_accel: float
            maximum acceleration in metres per second per second
        max_brake: float
            maximum brake in metres per second per second
        max_speed: float
            maximum speed in metres per second
        max_tyre_life: integer
            nominal maximum tyre life in metres, when tyre_wear = max_tyre_life: tyre_deg = 1
        cornering: float
            cornering performance, 1 is average, <1 is better, >1 is worse
        drive_style: float
            driving style, 1 is average, <1 is cautious, >1 is aggressive
        pit_lap: integer
            the lap on which the car will enter pits, 1 means stop at end of first lap
        box_time: float
            the time in seconds that the car is stationary in pits
        box_location: float
            the time in seconds that the car takes to reach it's pit box from pit entry
    """
    
    
    def __init__(self, name, max_accel, max_brake, max_speed, max_tyre_life, \
                 cornering, drive_style, pit_lap, box_time, box_location):
        self.name = name
        self.max_accel = max_accel
        self.max_brake = max_brake
        self.max_speed = max_speed
        self.cornering = cornering
        self.drive_style = drive_style
        self.accel = max_accel
        self.brake = max_brake
        self.speed = 0
        self.distance = 0
        self.distance_travel = 0
        self.max_tyre_life = max_tyre_life
        self.tyre_wear = 0
        self.tyre_deg = 0
        self.tyre_perf = 1
        self.tyre_corner_penalty = 0
        self.lap_count = 0 # where 1 means first lap completed
        self.pit_lap = pit_lap
        self.box_time = box_time
        self.box_location = box_location
        self.stopped = False
        self.in_pit = False
        self.pit_duration = 0
        self.next_corner = 0 # index of corner in track.corner_list - initially the first corner
        
        
    # define a repr function
    def __repr__(self):
        return self.name
    
    # define a lap_loc method
    def lap_location(self, lap_length):
        return (self.distance - (self.lap_count * lap_length))
    
    # define a calc_tyre_perf method
    def calc_tyre_perf(self, max_fuel_effect, race_distance):
        
        # calculate fuel effect
        fuel_effect = 1 + (max_fuel_effect * ((race_distance - self.distance) / race_distance))
        
        # calculate tyre_wear
        self.tyre_wear += (self.distance_travel + self.tyre_corner_penalty) * fuel_effect
        
        # calculate tyre_deg
        self.tyre_deg = self.tyre_wear / self.max_tyre_life
        
        # calculate tyre_perf
        self.tyre_perf = max((1 - self.tyre_deg**2), 0.25)
        
    # define calc_accel method
    def calc_accel(self, max_fuel_effect, race_distance):
        self.accel = self.max_accel * self.tyre_perf * \
        (1 - (max_fuel_effect * ((race_distance - self.distance) / race_distance)))
        
    # define calc_brake method
    def calc_brake(self, max_fuel_effect, race_distance):
        self.brake = self.max_brake * self.tyre_perf * \
        (1 - (max_fuel_effect * ((race_distance - self.distance) / race_distance)))


class Track:
    
    """simulates a race track
        
        parameters
        ----------
        name: str
            instance name
        lap_length: float
            total length of a lap of the track in metres
        pit_length: integer
            total time in seconds for a car to travel the length of the pit lane at the pit_speed_limit
        pit_speed_limit: integer
            speed limit in pit lane in metres per second
        corner_list: list object
            list of Corner class objects
        lap_fuel_effect: float
            effect of one laps worth of fuel on performance as a percentage
        """
    
    # define an initialize function
    def __init__(self, name, lap_length, pit_length, pit_speed_limit, corner_list, lap_fuel_effect):
        self.name = name
        self.lap_length = lap_length
        self.pit_length = pit_length
        self.pit_speed_limit = pit_speed_limit
        self.corner_list = corner_list
        self.lap_fuel_effect = lap_fuel_effect
        

class Corner:
    
    """simulates a corner on a race track
    
        parameters
        ----------
        name: str
            instance name
        start: float
            distance from the start/finish line to the start of the corner in metres
        apex: float
            distance from the start/finish line to the apex of the corner in metres
        end: float
            distance from the start/finish line to the end of the corner in metres
        max_speed: float
            nominal maximum apex speed
        overtake: float
            speed advantage required to overtake another car on the corner
        """
    
    # define an initialize function
    def __init__(self, name, start, apex, end, max_speed, overtake):
        self.name = name
        self.start = start
        self.apex = apex
        self.end = end
        self.max_speed = max_speed
        self.speed = max_speed
        self.overtake = overtake
        
    # define a repr function
    def __repr__(self):
        return self.name
    
    # define a calc_apex_speed method
    def calc_apex_speed(self, car_tyre_perf, car_cornering):
        self.speed = self.max_speed * car_tyre_perf * car_cornering


def create_team_car(team_name, max_accel, max_brake, max_speed, max_tyre_life, \
                 cornering, drive_style, pit_lap, box_time):
    
    """creates the team car / car of interest with the specified attributes, sets up car_list and car_df

        arguments
        ----------
        team_name: str
            instance name
        max_accel: float
            maximum acceleration in metres per second per second
        max_brake: float
            maximum brake in metres per second per second
        max_speed: float
            maximum speed in metres per second
        max_tyre_life: integer
            nominal maximum tyre life in metres, when tyre_wear = max_tyre_life: tyre_deg = 1
        cornering: float
            cornering performance, 1 is average, <1 is better, >1 is worse
        drive_style: float
            driving style, 1 is average, <1 is cautious, >1 is aggressive
        pit_lap: integer
            the lap on which the car will enter pits, 1 means stop at end of first lap
        box_time: float
            the time in seconds that the car is stationary in pits 
    """
    
    # create the team car, box_location will be determined by qualifying position, set initially to 1
    team_car = Car(team_name, max_accel, max_brake, max_speed, max_tyre_life, \
                 cornering, drive_style, pit_lap, box_time, 1)
    
    # create car_list
    car_list = []
    
    # append team_car to car_list
    car_list.append(team_car)
    
    # create list of car attridutes
    team_attr = [[team_car.name, team_car.max_accel, team_car.max_brake, team_car.max_speed, team_car.max_tyre_life, \
                  team_car.cornering, team_car.drive_style, team_car.pit_lap, team_car.box_time, team_car.box_location]]
    
    # create car_df column list
    columns = ['Car', 'Max_Accel', 'Max_Brake', 'Max_Speed', 'Max_Tyre_Life', 'Cornering', 'Drive_Style', 'Pit_Lap', \
               'Box_Time', 'Box_Location']
    
    # create car_df
    car_df = pd.DataFrame(team_attr, columns = columns)
    
    # return the car_list and car_df
    return car_list, car_df


def create_competitors(car_list, car_df, no_comp, mean_max_accel, std_max_accel, mean_max_brake, std_max_brake, \
                       mean_max_speed, std_max_speed, mean_max_tyre_life, dif_max_tyre_life, \
                       mean_cornering, std_cornering, mean_drive_style, std_drive_style, pit_lap_list, box_time):
    
    """creates the specified number of competitor cars with attributes from the specified distributions

        arguments
        ----------
        car_list: list object
            list containing the team_car
        car_df: dataframe object
            dataframe containing the team car
        no_comp: integer
            number of competitors cars to be created
        mean_max_accel: float
            mean maximum acceleration in metres per second per second
        std_max_accel: float
            standard deviation of max_accel values
        mean_max_brake: float
            mean maximum brake in metres per second per second
        std_max_brake: float
            standard deviation of max_brake values
        mean_max_speed: float
            mean maximum speed in metres per second
        std_max_speed: float
            standard deviation of max_speed values
        mean_max_tyre_life: integer
            mean nominal maximum tyre life in metres, when tyre_wear = max_tyre_life: tyre_deg = 1
        dif_max_tyre_life: integer
            range of possible max_tyre_life values is given by mean_max_tyre_life +/- dif_max_tyre_life
        mean_cornering: float
            mean cornering performance, 1 is average, <1 is better, >1 is worse
        std_cornering: float
            standard deviation of cornering values
        mean_drive_style: float
            mean driving style, 1 is average, <1 is cautious, >1 is aggressive
        std_drive_style: float
            standard deviation drive_style values
        pit_lap_list: list object
            list of potential laps on which a competitor could enter pits, 1 means stop at end of first lap
        box_time: float
            the time in seconds that the car is stationary in pits
    """
    
    # create comp_list
    comp_list = []
    
    # create a car instance for each no_comp
    for i in range(no_comp):
        
        # set max_accel
        max_accel = round(random.normalvariate(mean_max_accel, std_max_accel), 2)
        
        # set max_brake
        max_brake = round(random.normalvariate(mean_max_brake, std_max_brake), 2)
        
        # set max_speed
        max_speed = round(random.normalvariate(mean_max_speed, std_max_speed), 2)
        
        # set max_tyre_life
        max_tyre_life = random.randint(mean_max_tyre_life - dif_max_tyre_life, mean_max_tyre_life + dif_max_tyre_life)
        
        # set cornering
        cornering = round(random.normalvariate(mean_cornering, std_cornering), 3)
        
        # set drive_style
        drive_style = round(random.normalvariate(mean_cornering, std_cornering), 3)
        
        # set pit_lap
        pit_lap = random.choice(pit_lap_list)
        
        # create a Car instance
        comp_list.append(Car('Car_{}'.format(i), max_accel, max_brake, max_speed, max_tyre_life, \
                 cornering, drive_style, pit_lap, box_time, 0))
        
    # add comp_list to car_list
    car_list = car_list + comp_list
    
    # iterate through cars in comp_list
    for i in range(len(comp_list)):
        
        # create list of car attributes
        car = comp_list[i]
        car_attr = [car.name, car.max_accel, car.max_brake, car.max_speed, car.max_tyre_life, car.cornering, \
                 car.drive_style, car.pit_lap, car.box_time, 0]
        
        # append car_attr to car_df
        car_df.loc[i + 1] = car_attr
        
    # return car_list and car_df
    return car_list, car_df


def qualifying(car_list, car_df, track, grid_offset):
    
    """determines the start_grid and updates the car_df

        arguments
        ----------
        car_list: list object
            list containing the team_car and competitor cars
        car_df: dataframe object
            dataframe containing the team car and competitor cars
        track: Track Class object
            Track for the qualifying session
        grid_offset: float
            the distance in metres between adjacent cars on the starting grid
    """
    
    # create qual_time_dict
    adj_qual_time_dict = {}
    
    # add qual_time, qual_dist and adj_qual_time columns to car_df
    car_df['Qual_Time'] = 0
    car_df['Qual_Dist'] = 0
    car_df['Adj_Qual_Time'] = 0
    
    # iterate through cars in car_list
    for car in car_list:
        
        # create qual_grid_dict for qualifying run
        qual_grid_dict = {0: car}
        
        # generate qualifying lap time - create qual_car_df in qualifying?
        qual_df, car_df = race(track, 2, qual_grid_dict, car_df, car_length, 1, False, 0)
        
        # omit out lap
        qual_lap_df = qual_df[qual_df.distance >= track.lap_length].reset_index()
        
        # calculate qualifying lap time (second / flying lap)
        qual_time = qual_lap_df['race_time'].iloc[-1] - qual_lap_df['race_time'].iloc[0]
        
        # calculate the qualifying distance (to break lap time ties)
        qual_dist = qual_lap_df['distance'].iloc[-1] - qual_lap_df['distance'].iloc[0]
        
        # adjust qual time according to qual_dist
        adj_qual_time = qual_time - (((qual_dist - track.lap_length) / track.lap_length) * (qual_time / 1.3))
        
        # save adj_qual_time: car to dict
        adj_qual_time_dict[adj_qual_time] = car
        
        # save qual_time, qual_dist and adj_qual_time to car_df
        car_df.loc[(car_df.Car == car.name), 'Qual_Time'] = qual_time
        car_df.loc[(car_df.Car == car.name), 'Qual_Dist'] = qual_dist
        car_df.loc[(car_df.Car == car.name), 'Adj_Qual_Time'] = adj_qual_time
        
        # reset finishing race_time in car_df
        car_df.loc[(car_df.Car == car.name), 'Finish_Time'] = 0
        
        # reset car attributes in preparation for race
        car.speed = 0
        car.tyre_wear = 0
        car.tyre_deg = 0
        car.tyre_perf = 1
        car.lap_count = 0
        
    # order adj_qual_times
    qual_time_order = sorted(list(adj_qual_time_dict.keys()))
    
    # create start_grid_dict
    start_grid_dict = {}
    
    # iterate through cars
    for i in range(len(qual_time_order)):
    
        # order cars by qualifying lap time
        car = adj_qual_time_dict.get(qual_time_order[i])
        
        # assign starting grid position
        start_grid_dict[i] = car
        
        # set car.distance according to grid position
        car.distance = -i * grid_offset
        
        # set car.box_location
        car.box_location = (i + 2) / 2
        
    # update car_df with start positions
    # add start_position column to car_df
    car_df['Start_Position'] = 0

    # iterate through grid positions
    for i in range(len(start_grid_dict)):
    
        # save grid position to car_df
        car_df.loc[(car_df.Car == start_grid_dict[i].name), 'Start_Position'] = i
        
        # save box_location to car_df
        car_df.loc[(car_df.Car == start_grid_dict[i].name), 'Box_Location'] = start_grid_dict[i].box_location
    
    # return start_grid_dict and car_df
    return start_grid_dict, car_df


def calc_brake_dist(current_speed, apex_speed, max_brake):
    
    """calculates the braking distance in metres based on the current speed and apex speed of the approaching corner
    
        arguments
        ----------
        current_speed: float
            the current speed of the car
        apex_speed: float
            the target apex speed of the car for the next corner
        max_brake: float
            the current maximum braking of the car
    """
    
    # calculate the time required to brake to apex_speed
    t = (current_speed - apex_speed) / -max_brake
    
    # define the velocity equation
    velocity = lambda x: current_speed + (max_brake * x)
    
    # calculate distance required to brake to apex_speed
    distance = quad(velocity, 0, t)
    
    # return distance
    return distance[0]


def solve_accel_brake_time_func(vel_0, max_accel, max_brake, dist_delta):
    
    """calculates the time period spent accelerating"""
    
    # define the accel_brake_time_func
    def accel_brake_time_func(t_a):
        
        return (vel_0*t_a) + (max_accel/2)*t_a**2 + vel_0*(t_b_ratio*t_a - t_a) - (max_brake/2)*(t_b_ratio*t_a - t_a)**2 - dist_delta

    # calculate t_b_ratio
    t_b_ratio = (-max_brake + max_accel) / (-max_brake)
    
    # try to solve accel_brake_time_func (values greater than 1 will cause an error)
    try:
        t_a = optimize.brentq(accel_brake_time_func, 0, 1)
        
    except:
        t_a = 1
    
    # return accel time
    return t_a


def solve_brake_time_func(vel_0, max_brake, dist_delta):
    
    """calculates the time period spent braking
        
        arguments
        ----------
        vel_0: float
            current speed of the car
        max_accel: float
            current maximum acceleration of the car
        max_brake: float
            current maximum braking of the car
        dist_delta: float
            distance in metres between the car's current position and the braking point
            (at current speed) for the next corner
    """
    
    # define the brake_time_func   
    def brake_time_func(t_b):
    
        return vel_0*t_b + (max_brake/2)*t_b**2 - dist_delta
    
    # try to solve brake_time_func (values greater than 1 will cause an error)
    try:
        t_b = optimize.brentq(brake_time_func, 0, 1)
        
    except:
        t_b = 1
    
    # return braking time
    return t_b


def update_vel(current_speed, accel_brake, time_increment):
    
    """calculates the new speed
        
        arguments
        ----------
        current_speed: float
            current speed of the car
        accel_brake: float
            current maximum acceleration or maximum braking of the car
        time_increment: float
            time in seconds spent accelerating or braking
    """
    
    vel = current_speed + accel_brake * time_increment
    return vel


def calc_dist(current_speed, time_increment, accel_brake, max_speed):
    
    """calculates the distance travelled while accelerating or braking, allowing for reaching max_speed
        
        arguments
        ----------
        current_speed: float
            current speed of the car
        time_increment: float
            time in seconds spent accelerating or braking
        accel_brake: float
            current maximum acceleration or maximum braking of the car
        max_speed: float
            the maximum speed of the car
    """
    
    # define the velocity equation
    velocity = lambda x: current_speed + (accel_brake * x)
    
    # check is speed is going to exceed max_speed
    if update_vel(current_speed, accel_brake, time_increment) > max_speed:
        
        # calculate time required to reach max_speed
        t_a = (max_speed - current_speed) / accel_brake
        
        # calculate distance travelled while accelerating
        dist_accel = quad(velocity, 0, t_a)
        
        # calculate distance travelled while at max_speed
        dist_max_speed = max_speed * (time_increment - t_a)
        
        # sum dist_accel and dist_max_speed
        distance = dist_accel[0] + dist_max_speed
        
    # if max_speed will not be exceeded
    else:
        
        # calculate distance travelled
        distance = quad(velocity, 0, time_increment)[0]
        
    # return distance
    return distance


def overtake(track, car, potential_dist, potential_speed, next_corner, prev_corner):
    
    """checks if a competitor car is within the potential_dist and determines whether it can be overtaken
        
        arguments
        ----------
        track: Track Class object
            the Track for the race
        car: Car Class object
            the current car
        potential_dist: float
            the maximum distance the car can travel if it is not stuck behind a competitor
        potential_speed: float
            the maximum speed the car could be travelling at if it is not stuck behind a competitor
        next_corner: Corner Class object
            the corner that the car is approaching
        prev_corner: Corner Class object
            the corner that the car is leaving
    """
    
    # set global variables
    global race_time
    global finished_cars
    global positions_dict
    global finished_cars
    global car_length
    global car_position
    global stuck_behind
    global debug
    
    # set stuck_behind
    # stuck_behind = False
    
    # check if there is another car within the max_dist
    # iterate through cars in front starting with the car immediately in front
    
    # if car is not leading
    if car_position == 0:
        
        # set distance_travel to potential_dist
        car.distance_travel = potential_dist
        
        # set speed to potential_speed
        car.speed = potential_speed
        
    # for all other cars    
    else:
        
        # iterate through cars in front (starting with one position ahead)
        for x in range((-car_position + 1), 1):
                        
            # set car_in_front variable
            car_in_front = positions_dict[-x]
                        
            # check if car is behind car_in_front 
            if (car.distance + potential_dist) <= car_in_front.distance - car_length:
                            
                # set distance_travel to potential_dist
                car.distance_travel = potential_dist
                
                # set speed to potential_speed
                car.speed = potential_speed
                                
                # leave car_in_front for loop
                break
                            
            # else car.distance + potential_dist is greater than car_in_front.distance - car_length
            # car is either alongside or in front
            else:
                        
                # check if car_in_front has finished race
                if car_in_front in finished_cars:
                                    
                    # set distance_travel to potential_dist
                    car.distance_travel = potential_dist
                    
                    # set speed to potential_speed
                    car.speed = potential_speed
                                    
                    # leave car_in_front for loop
                    break
                            
                # check if car_in_front is in the pits
                elif car_in_front.in_pit == True:

                    # insert temp debug option
                    if debug >= 1:
                        print(f'{str(race_time)}: {car} overtake arguments are: {next_corner}, {prev_corner}.')
                                
                    # car is on track and not entering pits
                    if (car.in_pit == False) & (next_corner.name != 'Pit Entry'):
                        
                        # set distance_travel to potential_dist
                        car.distance_travel = potential_dist
                    
                        # set speed to potential_speed
                        car.speed = potential_speed
                        
                        # if (car.distance + potential_dist) > car_in_front.distance car overtakes
                        # else car is alongside
                        if (car.distance + potential_dist) > car_in_front.distance:
                            
                            # change positions_dict
                            positions_dict[-x] = car
                            positions_dict[-x+1] = car_in_front
                            
                            # change car_position
                            car_position = -x
                                
                            # debug option
                            if debug >= 1:
                                print(f'{str(race_time)}: {car} has overtaken {car_in_front} while in pit.')
                    
                    # else if car is entering pits or in pits and car_in_front is in pit box
                    elif car_in_front.speed == 0:
                        
                        # set distance_travel to potential_dist
                        car.distance_travel = potential_dist
                    
                        # set speed to potential_speed
                        car.speed = potential_speed
                        
                        # if (car.distance + potential_dist) > car_in_front.distance car overtakes
                        # else car is alongside
                        if (car.distance + potential_dist) > car_in_front.distance:
                            
                            # change positions_dict
                            positions_dict[-x] = car
                            positions_dict[-x+1] = car_in_front
                            
                            # change car_position
                            car_position = -x
                                
                            # debug option
                            if debug >= 1:
                                print(f'{str(race_time)}: {car} has overtaken {car_in_front} while in pit box.')
                    
                    # else car is entering pits or in pits and car_in_front is travelling down pit lane
                    else:
                    
                        # set distance_travel to potential_dist
                        car.distance_travel = car_in_front.distance - car.distance - car_length
                    
                        # set speed to potential_speed
                        car.speed = min(car_in_front.speed, potential_speed)
                            
                        # debug option
                        if debug >= 2:
                            print(f'{str(race_time)}: {car} is stuck behind {car_in_front} in pit lane.')
                                        
                        # can end car time_increment, car cannot travel further
                        stuck_behind = True
                        
                        # leave car_in_front for loop
                        break
                        
                # else car_in_front is on track
                else:
                    
                    # identify location of car on lap - current location before any action is taken
                    car_lap_dist = car.distance - (track.lap_length * car.lap_count)
                    
                    # check if car is still on prev_corner
                    if prev_corner.start < car_lap_dist < prev_corner.end:
                        
                        # set overtake_req
                        overtake_req = prev_corner.overtake
                    
                    # check if car has entered next_corner
                    elif next_corner.start < car_lap_dist < next_corner.end:
                        
                        # set overtake_req
                        overtake_req = next_corner.overtake
                        
                    # else car is on straight
                    else:
                        
                        # set overtake_req
                        overtake_req = 0
                        
                    # debug option
                    if debug >= 4:
                        print(f'{str(race_time)}: Overtake requirement for {car} is {overtake_req}.')
                    
                    # check if speed delta is greater than overtake_req
                    if ((potential_speed - car_in_front.speed) >= overtake_req) | (overtake_req == 0):
                        
                        # if car is alongside
                        if (car.distance + potential_dist) < car_in_front.distance:
                            
                            # set distance_travel to potential_dist
                            car.distance_travel = potential_dist
                    
                            # set speed to potential_speed
                            car.speed = potential_speed
                            
                            # debug option
                            if debug >= 2:
                                print(f'{str(race_time)}: {car} is alongside {car_in_front}.')
                        
                        # else car is in front
                        else:
                            
                            # set distance_travel to potential_dist
                            car.distance_travel = potential_dist
                        
                            # set speed to potential_speed
                            car.speed = potential_speed
                            
                            # change positions_dict
                            positions_dict[-x] = car
                            positions_dict[-x+1] = car_in_front
                            
                            # change car_position
                            car_position = -x
                            
                            # debug option
                            if debug >= 1:
                                print(f'{str(race_time)}: {car} has overtaken {car_in_front}.') 
                        
                    # else car is stuck behind car_in_front
                    else:
                            
                        # set distance_travel to a restricted value
                        car.distance_travel = car_in_front.distance - car.distance - car_length
                        
                        # set speed
                        car.speed = min(car_in_front.speed, potential_speed)
                            
                        # debug option
                        if debug >= 2:
                            print(f'{str(race_time)}: {car} is stuck behind {car_in_front}.')
                            
                        # can end car time_increment, car cannot travel further
                        stuck_behind = True
                        
                        # check if car.distance will be less than overtaken cars (due to car_length)
                        # iterate through cars behind (starting with two positions behind / one behind is car)
                        # could possibly switch back places with cars in pit lane but 
                        # unlikely as can't get stuck behind car on a straight
                        # problem is could be repassed by car_in_front even if only alongside not overtaking
                        for k in range((-x+2), len(positions_dict)):
                            
                            # set car_behind variable
                            car_behind = positions_dict[k]
                            
                            # check distance_travel
                            if (car.distance_travel < car_behind.distance - car.distance) & (k > car_position):
                                
                                # switch positions (car could not complete overtake)
                                # change positions_dict
                                positions_dict[k-1] = car_behind
                                positions_dict[k] = car
                            
                                # change car_position
                                car_position = k
                                
                                # debug option
                                if debug >= 1:
                                    print(f'{str(race_time)}: {car} has been repassed by {car_behind}.') 
                            
                            # if car.distance is greater than car_behind don't need to check remainder 
                            else:
                                
                                # leave car_behind loop
                                break
                                        
                        # leave car_in_front for loop
                        break


def race(track, race_laps, start_grid_dict, car_df, car_length_val, time_period, race_time_limit, debug_val):
    
    """runs a simulation of a race
        
        arguments
        ----------
        track: Track Class object
            the Track for the race
        race_laps: integer
            the length of the race in laps
        start_grid_dict: dictionary object
            dictionary with position keys and car values
        car_df: dataframe object
            dataframe containing the team car and competitor cars
        car_length_val: float
            distance in metres between a leading car and the car stuck behind it
        time_period: float
            race time duration in seconds of each iteration of the race function
        race_time_limit: Boolean
            True if race to stop after 90 seconds, else False
        debug_val: integer
            controls level of race progress output, 0 is none, 4 is maximum
    """
    
    # set global variables
    global race_time
    global finished_cars
    global positions_dict
    global finished_cars
    global car_length
    global car_position
    global stuck_behind
    global debug
    
    ## store car positions
    positions_dict = copy.deepcopy(start_grid_dict)
    
    ## copy the car_df
    sim_car_df = copy.deepcopy(car_df)
    
    ## create list of cars
    car_list = list(start_grid_dict.values())
    
    ## create a list of column headers
    column_list = ['car', 'car_name', 'race_time', 'lap', 'position', 'distance', 'speed', 'tyre_wear', 'tyre_performance']
    
    ## create the race_df
    race_df = pd.DataFrame(columns = column_list)
    
    # create finish_position column in car_df
    sim_car_df['Finish_Position'] = 0
    
    # create finish_time column in car_df
    sim_car_df['Finish_Time'] = 0
    
    # set race_finished to False
    race_finished = False
    
    # set car_length
    car_length = car_length_val
    
    # set race_distance
    race_distance = track.lap_length * race_laps
    
    # set max_fuel_effect
    max_fuel_effect = track.lap_fuel_effect * race_laps
    
    # set debug
    debug = debug_val
    
    # reset race_time
    race_time = timedelta(seconds = 0)
    
    # check if time_limit is required
    if race_time_limit == True:
        
        # set time_limit
        time_limit = timedelta(seconds = 90)
        
    else:
        # set time_limit to arbitary value
        time_limit = timedelta(seconds = 0)
    
    # reset finished_cars list / store cars that have finished the race
    finished_cars = []
    
    while (race_finished == False) & ((race_time < time_limit) | (race_time_limit == False)):
    
        # check if all cars have finished the race
        if len(finished_cars) == len(car_list):
        
            # race complete return result
            race_finished = True
            
        # if not continue race
        else:
    
            # cycle through the cars in order of position
            for i in range(len(car_list)):
                
                # set car variable as the current car
                car = positions_dict[i]
                
                # set car_position variable
                car_position = i
                
                # debug option
                if debug >= 3:
                    print(f'{str(race_time)}: {car} is current car in position {i}, on lap {(car.lap_count + 1)}')
                
                # check if car has finished race
                if car in finished_cars:
                
                    # continue to next car 
                    continue
                
                # check if car completed a lap at last iteration
                if car.distance - (car.lap_count * track.lap_length) > track.lap_length:
                        
                    # update car.lap_count
                    car.lap_count += 1
                                           
                    # debug option
                    if debug >= 1:
                        print(f'{str(race_time)}: {car} has completed lap {car.lap_count} in position {i}')
                
                # check if car finished race at last iteration
                if car.distance > track.lap_length * race_laps:
                
                    # add car to finished cars
                    finished_cars.append(car)
                    
                    # add finishing position to car_df
                    sim_car_df.loc[(sim_car_df.Car == car.name), 'Finish_Position'] = i
                    
                    # add finishing race_time to car_df
                    sim_car_df.loc[(sim_car_df.Car == car.name), 'Finish_Time'] = race_time
                                      
                    # debug option
                    if debug >= 1:
                        print(f'{str(race_time)}: {car} has been added to finished_cars')
                    
                    # continue to next car
                    continue
                
                # determine seperate time_increment for continue / accelerate / brake actions
                # for each time_increment return time_increment value, current_speed, distance travelled
                
                # set sum_time_increment
                sum_time_increment = 0
                
                # set sum_dist_increment
                sum_dist_increment = 0
                
                # set stuck_behind
                stuck_behind = False
                
                # determine actions during time period
                while (round(sum_time_increment, 2) < time_period) & (stuck_behind == False):
                    
                    # check if car is in pits
                    if car.in_pit == True:
                                          
                        # reset car tyre_corner_penalty
                        car.tyre_corner_penalty = 0
                        
                        # determine car position
                        # is car approching box
                        if car.pit_duration < car.box_location:
                            
                            # calculate time_increment
                            # a minimum time increment of 0.005 avoids repeated iterations with negligible effects 
                            t_p = max(0.005, min(1, (1-sum_time_increment), (car.box_location - car.pit_duration)))
                            
                            # proceed down pit lane to box
                            potential_dist = t_p * track.pit_speed_limit
                            
                            # set potential_speed to pit_speed_limit
                            potential_speed = track.pit_speed_limit
                                                     
                            # check for overtake
                            overtake(track, car, potential_dist, potential_speed, next_corner, prev_corner)
                            
                            # update car.distance
                            car.distance += car.distance_travel
                            
                            # update sum_dist_increment
                            sum_dist_increment += car.distance_travel
                                                     
                            # update pit_duration
                            car.pit_duration += t_p
                            
                            # update sum_time_increment
                            sum_time_increment += t_p
                            
                            # append data to race_df
                            race_df = race_df.append(
                            {'car': car, 'car_name': car.name, \
                             'race_time': (race_time + timedelta(seconds=sum_time_increment)).total_seconds(), \
                             'lap': car.lap_count, 'position': int(i), 'distance': car.distance, 'speed': car.speed, \
                             'tyre_wear': float(car.tyre_wear), 'tyre_performance': car.tyre_perf}, ignore_index=True)
                            
                            # debug option
                            if debug >= 3:
                                print(f'{str(race_time)}: {car} is in pit lane, approaching box, t_p = {t_p}')
                        
                        # is car in pit box
                        elif car.pit_duration < (car.box_location + car.box_time):
                            
                            # calculate time increment
                            t_p = max(0.005, min(1, (1-sum_time_increment), \
                                                     (car.box_location + car.box_time - car.pit_duration)))
                    
                            # update tyre attributes
                            car.tyre_wear = 0
                            car.tyre_deg = 0
                            car.tyre_perf = 1
                        
                            # update car speed
                            car.speed = 0
                            
                            # update pit_duration
                            car.pit_duration += t_p
                            
                            # update sum_time_increment
                            sum_time_increment += t_p
                            
                            # append data to race_df
                            race_df = race_df.append(
                            {'car': car, 'car_name': car.name, \
                             'race_time': (race_time + timedelta(seconds=sum_time_increment)).total_seconds(), \
                             'lap': car.lap_count, 'position': int(i), 'distance': car.distance, 'speed': car.speed, \
                             'tyre_wear': float(car.tyre_wear), 'tyre_performance': car.tyre_perf}, ignore_index=True)
                            
                            # debug option
                            if debug >= 3:
                                print(f'{str(race_time)}: {car} is in pit lane, in box, t_p = {t_p}')
                             
                        # has car left box
                        elif car.pit_duration < (track.pit_length + car.box_time):
                    
                            # calculate time_increment
                            t_p = max(0.005, min(1, (1-sum_time_increment), \
                                                     (track.pit_length + car.box_time - car.pit_duration)))
                            
                            # proceed down pit lane to exit
                            potential_dist = t_p * track.pit_speed_limit
                            
                            # set potentail_speed to pit_speed_limit
                            potential_speed = track.pit_speed_limit
                            
                            # check for overtake
                            overtake(track, car, potential_dist, potential_speed, next_corner, prev_corner)
                            
                            # update car.distance
                            car.distance += car.distance_travel
                            
                            # update sum_dist_increment
                            sum_dist_increment += car.distance_travel
                                                     
                            # update pit_duration
                            car.pit_duration += t_p
                            
                            # update sum_time_increment
                            sum_time_increment += t_p
                            
                            # append data to race_df
                            race_df = race_df.append(
                            {'car': car, 'car_name': car.name, \
                             'race_time': (race_time + timedelta(seconds=sum_time_increment)).total_seconds(), \
                             'lap': car.lap_count, 'position': int(i), 'distance': car.distance, 'speed': car.speed, \
                             'tyre_wear': float(car.tyre_wear), 'tyre_performance': car.tyre_perf}, ignore_index=True)
                            
                            # debug option
                            if debug >= 3:
                                print(f'{str(race_time)}: {car} is in pit lane, leaving box, t_p = {t_p}')
                            
                        # car exits pit
                        else:
                                                    
                            # car leaves the pits
                            car.in_pit = False
                        
                            # debug option
                            if debug >= 1:
                                print(f'{str(race_time)}: {car} has left the pits')
                        
                        # continue to next increment / car
                        continue
                    
                    # alternative identify next_corner / prev_corner routine
                    next_corner = track.corner_list[car.next_corner]
                    
                    # debug option
                    if debug >= 3:
                        print(f'{car} approaching {next_corner}.')
                    
                    prev_corner = track.corner_list[(car.next_corner - 1)]
                    
                    # omit pit_entry from prev_corner variable
                    if prev_corner.name == 'Pit Entry':
                                
                        # select corner before pit_entry
                        prev_corner = track.corner_list[(car.next_corner - 2)]
                        
                    # debug option
                    if debug >= 4:
                        print(f'{car} previous corner is {prev_corner}.')
                    
                    # update car tyre_perf
                    car.calc_tyre_perf(max_fuel_effect, race_distance)
                    
                    # update car accel
                    car.calc_accel(max_fuel_effect, race_distance)
                    
                    # update car brake
                    car.calc_brake(max_fuel_effect, race_distance)
                    
                    # reset car tyre_corner_penalty
                    car.tyre_corner_penalty = 0
                    
                    # calculate next_corner apex speed
                    next_corner.calc_apex_speed(car.tyre_perf, car.cornering)
                    
                    # calculate car apex speed allowing for car.drive_style
                    car_apex_speed = next_corner.speed * car.drive_style
                    
                    # calculate distance to next apex (apex_dist)
                    apex_dist = round((next_corner.apex + (track.lap_length * car.lap_count) - car.distance), 3)
                    
                    # for first corner in next lap apex_dist will be negative - add lap_length
                    if apex_dist < 0:
                        
                        apex_dist += track.lap_length
                    
                    # debug option
                    if debug >= 4:
                        print(f'Apex distance = {apex_dist}.')
            
                    # calculate brake_dist at current speed for next apex (allowing for car.drive_style)
                    brake_dist = round(calc_brake_dist(car.speed, car_apex_speed, car.brake), 3)
                    
                    # debug option
                    if debug >= 4:
                        print(f'Brake distance = {brake_dist}.')
            
                    # calculate difference between apex_dist and brake_dist (dist_delta)
                    dist_delta = (apex_dist - brake_dist)
                    
                    # debug option
                    if debug >= 4:
                        print(f'Distance delta = {dist_delta}.')
    
                    # is dist_delta <= 0
                    if round(dist_delta, 1) <= 0:
                        
                        # break for t_b (until apex is reached or (1 - sum_time_increment))
                        t_b = max(0.005, min(
                            ((car.speed - car_apex_speed)/-car.brake), solve_brake_time_func(
                                car.speed, car.brake, apex_dist), (1-sum_time_increment)))
                        
                        # calculate potential distance travelled
                        potential_dist = round(calc_dist(car.speed, t_b, car.brake, car.max_speed), 5)
                        
                        # calculate potential car.speed
                        potential_speed = update_vel(car.speed, car.brake, t_b)
                        
                        # check for overtake
                        overtake(track, car, potential_dist, potential_speed, next_corner, prev_corner)
                        
                        # update car.distance
                        car.distance += car.distance_travel
                                               
                        # update sum_dist_increment
                        sum_dist_increment += car.distance_travel
                        
                        # update sum_time_increment
                        sum_time_increment += t_b
                        
                        # append data to race_df
                        race_df = race_df.append(
                        {'car': car, 'car_name': car.name, \
                         'race_time': (race_time + timedelta(seconds=sum_time_increment)).total_seconds(), \
                         'lap': car.lap_count, 'position': int(i), 'distance': car.distance, 'speed': car.speed, \
                         'tyre_wear': float(car.tyre_wear), 'tyre_performance': car.tyre_perf}, ignore_index=True)
                        
                        # debug option
                        if debug >= 3:
                            print(f'{str(race_time)}: {car} braked {car.distance_travel} in {t_b}, speed = {car.speed}.')
                        
                    # is dist_delta > 0
                    # car can accelerate or continue at max_speed until braking point is reached
                    # determine t_a or t_c (time accelerating or maintaining max_speed)
                    else:
                        
                        # if car.speed = car.max_speed: speed, brake_dist are constant
                        if car.speed >= car.max_speed:
                            
                            # determine t_c (time_increment spent at max_speed)
                            t_c = max(0.005, min((dist_delta / car.max_speed), (1-sum_time_increment)))
                            
                            # calculate potential_dist
                            potential_dist = round(calc_dist(car.speed, t_c, car.accel, car.max_speed), 5)
                            
                            # set potential_speed
                            potential_speed = car.max_speed
                            
                            # check for overtake
                            overtake(track, car, potential_dist, potential_speed, next_corner, prev_corner)
                            
                            # update car.distance
                            car.distance += car.distance_travel
                            
                            # update sum_dist_increment
                            sum_dist_increment += car.distance_travel
                            
                            # update sum_time_increment
                            sum_time_increment += t_c
                            
                            # append data to race_df
                            race_df = race_df.append(
                            {'car': car, 'car_name': car.name, \
                             'race_time': (race_time + timedelta(seconds=sum_time_increment)).total_seconds(), \
                             'lap': car.lap_count, 'position': int(i), 'distance': car.distance, 'speed': car.speed, \
                             'tyre_wear': float(car.tyre_wear), 'tyre_performance': car.tyre_perf}, ignore_index=True)
                            
                            # debug option
                            if debug >= 3:
                                print(f'{str(race_time)}: {car} continued {car.distance_travel} in {t_c}, speed = {car.speed}.')
                            
                            
                        # if car can accelerate
                        else:
                            
                            # determine t_a (time increment spent accelerating)
                            # t_a will equal the minimum of:
                            # time to accelerate to max_speed or
                            # maximum possible time accelerating before braking point is reached or
                            # time increment remaining
                            
                            # calculate time to accelerate to max_speed
                            t_a_max_speed = (car.max_speed - car.speed) / car.accel
                            
                            # calculate maximum possible time accelerating before braking point is reached
                            t_a_brake_point = solve_accel_brake_time_func(car.speed, car.accel, car.brake, dist_delta)
                            
                            # determine t_a_min
                            t_a = max(0.005, min(t_a_max_speed, t_a_brake_point, (1-sum_time_increment)))
                            
                            # calculate potential_dist
                            potential_dist = round(calc_dist(car.speed, t_a, car.accel, car.max_speed), 5)
                            
                            # calculate potential_speed
                            potential_speed = min(car.max_speed, update_vel(car.speed, car.accel, t_a))
                            
                            # check for overtake
                            overtake(track, car, potential_dist, potential_speed, next_corner, prev_corner)
                            
                            # update car.distance
                            car.distance += car.distance_travel
                            
                            # update sum_dist_increment
                            sum_dist_increment += car.distance_travel
                            
                            # update sum_time_increment
                            sum_time_increment += t_a
                            
                            # append data to race_df
                            race_df = race_df.append(
                            {'car': car, 'car_name': car.name, \
                             'race_time': (race_time + timedelta(seconds=sum_time_increment)).total_seconds(), \
                             'lap': car.lap_count, 'position': int(i), 'distance': car.distance, 'speed': car.speed, \
                             'tyre_wear': float(car.tyre_wear), 'tyre_performance': car.tyre_perf}, ignore_index=True)
                            
                            # debug option
                            if debug >= 3:
                                print(f'{str(race_time)}: {car} accelerated {car.distance_travel} in {t_a}, speed = {car.speed}.')
                                
                    # check if car is at corner apex
                    # if car is at apex compare next_corner.speed to actual car.speed
                    if round(car.distance_travel, 2) >= round(apex_dist, 2):
                            
                        # calculate speed_delta
                        speed_delta = car.speed - next_corner.speed
                            
                        # calculate car.tyre_corner_penalty
                        car.tyre_corner_penalty = max(0, (speed_delta**3 * (next_corner.end - next_corner.start)))
                            
                        # debug option
                        if debug >= 4:
                            print(f'{car} speed_delta = {speed_delta}, tyre_corner_penalty = {car.tyre_corner_penalty}.')
                                
                        # check if car has entered pits
                        if next_corner.name == 'Pit Entry':
                            
                            # update car.in_pit
                            car.in_pit = True
                            
                            # debug option
                            if debug >= 1:
                                print(f'{str(race_time)}: {car} has entered the pits.')
                                    
                        # update next_corner - alternative routine
                        car.next_corner = ((car.next_corner + 1) % len(track.corner_list))
                            
                        # check if car is due in pits
                        if (track.corner_list[car.next_corner].name == 'Pit Entry') & \
                        ((car.lap_count + 1) != car.pit_lap):
                                
                            # skip to next corner
                            car.next_corner = ((car.next_corner + 1) % len(track.corner_list))
                            
                # debug option
                if debug >= 2:
                    print(f'{str(race_time)}: {car} travelled {sum_dist_increment}, distance = {car.distance}, speed = {car.speed}.')
                
            # update race_time
            race_time += timedelta(seconds=1)
            
    # return result
    return race_df, sim_car_df


def plot_car_result(race_df, car_list, pos_list, period=False, period_start=None, period_end=None):
    
    """plots the speed, tyre_performance and position
        for the specified cars over the specified period
        or by default the entire race for a single simulation
    
        arguments
        ----------
        race_df: dataframe
            the race_df for the simulation
        car_list: list
            the car_list for the simulation
        pos_list: list
            a list of the car_list index values for the cars of interest
        period: boolean
            boolean value specifying if a particular period is required (default: False)
        period_start: float
            start time of specified period (default: None)
        period_end: float
            end time of specified period (default: None)
    """
    
    # create figure
    fig = plt.figure(figsize=(24, 26))
    
    # create first subplot / position
    ax1 = plt.subplot(3, 1, 1)
    
    # create second subplot / speed
    ax2 = plt.subplot(3, 1, 2)
    
    # create third subplot / tyre_wear
    ax3 = plt.subplot(3, 1, 3)
    
    # create plots for each car in pos_list
    for i in pos_list:
        
        # create race_df_car
        race_df_car = race_df[race_df.car_name == car_list[i].name]
        
        # select period if required
        if period == True:
            
            race_df_car = race_df_car[(race_df_car['race_time'] >= period_start) & (race_df_car['race_time'] < period_end)]
        
        # plot position against race_time
        ax1.plot(race_df_car['race_time'], race_df_car['position'], label=car_list[i])
        
        # plot speed against race_time
        ax2.plot(race_df_car['race_time'], race_df_car['speed'], label=car_list[i])

        # plot tyre_performance against race_time
        ax3.plot(race_df_car['race_time'], race_df_car['tyre_performance'], label=car_list[i])
    
        
    # set ax1 y axis ticks     
    ax1.set_yticks(list(range(len(car_list))))
    ax1.invert_yaxis()

    # set ax1 axis labels
    ax1.set_xlabel('Race Time')
    ax1.set_ylabel('Position')
    
    # set ax2 axis labels
    ax2.set_xlabel('Race Time')
    ax2.set_ylabel('Speed')
    
    # set ax3 axis labels
    ax3.set_xlabel('Race Time')
    ax3.set_ylabel('Tyre Performance')
    
    plt.legend()
    
    fig.suptitle('Race Results')
    
    plt.show()


def plot_sim_result(race_df_list, car_list_list, pos, period=False, period_start=None, period_end=None):
    
    """plots the speed, tyre_performance and position
        for a single car over the specified period
        or by default the entire race for multiple simulations
    
        arguments
        ----------
        race_df_list: list
            a list of the race_dfs for the simulations
        car_list_list: list
            a list of the car_lists for the simulations
        pos: integer
            the car_list index value for the car of interest
        period: boolean
            boolean value specifying if a particular period is required (default: False)
        period_start: float
            start time of specified period (default: None)
        period_end: float
            end time of specified period (default: None)
    """
    
    # create figure
    fig = plt.figure(figsize=(24, 26))
    
    # create first subplot / position
    ax1 = plt.subplot(3, 1, 1)
    
    # create second subplot / speed
    ax2 = plt.subplot(3, 1, 2)
    
    # create third subplot / tyre_wear
    ax3 = plt.subplot(3, 1, 3)
    
    # select car
    # car = car_list[pos]
    
    # create plots for each sim in race_df_list
    for i in range(len(race_df_list)):
        
        # select car
        car = car_list_list[i][pos]
        
        # select race_df
        race_df = race_df_list[i]
        
        # create race_df_car
        race_df_car = race_df[race_df.car_name == car.name]
        
        # select period if required
        if period == True:
            
            race_df_car = race_df_car[(race_df_car['race_time'] >= period_start) & (race_df_car['race_time'] < period_end)]
        
        # plot position against race_time
        ax1.plot(race_df_car['race_time'], race_df_car['position'], label=race_df.name)
        
        # plot speed against race_time
        ax2.plot(race_df_car['race_time'], race_df_car['speed'], label=race_df.name)

        # plot tyre_performance against race_time
        ax3.plot(race_df_car['race_time'], race_df_car['tyre_performance'], label=race_df.name)
        
    # set ax1 y axis ticks     
    ax1.set_yticks(list(range(len(car_list_list[0]))))
    ax1.invert_yaxis()

    # set ax1 axis labels
    ax1.set_xlabel('Race Time')
    ax1.set_ylabel('Position')
    
    # set ax2 axis labels
    ax2.set_xlabel('Race Time')
    ax2.set_ylabel('Speed')
    
    # set ax3 axis labels
    ax3.set_xlabel('Race Time')
    ax3.set_ylabel('Tyre Performance')
    
    plt.legend()
    
    fig.suptitle(t='Race Results', size='x-large')
    
    plt.show()


def plot_parameters(car_df):
    
    """plots multiple scatter plots showing
        Max_Accel, Max_Brake, Max_Speed, Max_Tyre_Life,
        Cornering and Drive_Style against Finish_Position
    
        arguments
        ----------
        car_df: dataframe
            the car_df dataframe for the simulation
    """
    
    # create figure
    fig = plt.figure(figsize=(24, 12))
    
    # create subplots
    axs = fig.subplots(2, 3)
      
    # create parameter list
    param_list = ['Max_Accel', 'Max_Brake', 'Max_Speed', 'Max_Tyre_Life', 'Cornering', 'Drive_Style']
    
    # create plots for each car in pos_list
    for i in range(len(param_list)):
            
        # plot param against Finish_Position
        axs[math.floor(i / 3), i%3].scatter(car_df['Finish_Position'], car_df[param_list[i]], marker='s')
        
        # add horizontal line at mean value
        mean_param = car_df[param_list[i]].mean()
        axs[math.floor(i / 3), i%3].hlines(mean_param, 0, 20, color = 'red', linestyles='dashed')
        
        # set x axis ticks
        axs[math.floor(i / 3), i%3].set_xticks(range(0, len(car_df['Finish_Position']), 5))
        
        # set x axis label
        axs[math.floor(i / 3), i%3].set_xlabel('Finish_Position')
        
        # set y axis label
        axs[math.floor(i / 3), i%3].set_ylabel(param_list[i])
        
    fig.suptitle('Car Parameters against Finish Position', size='x-large')
    
    plt.tight_layout()
    
    plt.show()