from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket
import math
import time

'''
Todo:
not trying to hit the ball if its above the bot
after the bot goes to the predicted goal place, it should try and intrecept the ball on its way to the goal
'''

def distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


class TutorialBot(BaseAgent):
    def __init__(self, name, team, index):
        super().__init__(name, team, index)
        self.controller = SimpleControllerState()

        # Contants
        self.DODGE_TIME = 0.2
        self.DISTANCE_TO_DODGE = 500
        self.DISTANCE_FROM_BALL_TO_BOOST = 1500  # The minimum distance the ball needs to be away from the bot for the bot to boost
        self.BALL_RADIUS = 92.75
        # The angle (from the front of the bot to the ball) at which the bot should start to powerslide.
        self.POWERSLIDE_ANGLE = math.radians(170)

        # Game values
        self.bot_pos = None
        self.bot_yaw = None
        self.time = None

        # Dodging
        self.should_dodge = False
        self.on_second_jump = False
        self.next_dodge_time = 0

    def predict_path(self):
        ball_prediction = self.get_ball_prediction_struct()
        predictions = {}
        if ball_prediction is not None:
            for i in range(0, ball_prediction.num_slices):
                prediction_slice = ball_prediction.slices[i]
                location = prediction_slice.physics.location
                predictions[prediction_slice.game_seconds] = location
        return predictions

    def will_be_goal(self, path):
        for key, value in path.items():
            if value.z < 640 and -890 + self.BALL_RADIUS < value.x < 890 - self.BALL_RADIUS and (value.y > 5120 or value.y < -5120):
                return (key, value)
        return (-1, -1)
    
    '''def time_to_hit(self, car, bot_pos, ball_pos):
        #values.game_info.seconds_elapsed = game time
        goal_loc = self.will_be_goal(self.predict_path()) 
        timer = goal_loc[1] - self.time #amount of seconds to get to the location
        self.aim(goal_loc[0].x, goal_loc[0].y)'''

    def emergency(self): #This function is called when a goal is detected
        #facing = get_car_facing_vector(car)
        goal_loc = self.will_be_goal(self.predict_path()) 
        #timer = goal_loc[1] - self.time #amount of seconds to get to the location
        self.aim(goal_loc[1].x, goal_loc[1].y)

    
    def aim(self, target_x, target_y):
        angle_between_bot_and_target = math.atan2(target_y - self.bot_pos.y,
                                                target_x - self.bot_pos.x)

        angle_front_to_target = angle_between_bot_and_target - self.bot_yaw

        # Correct the values
        if angle_front_to_target < -math.pi:
            angle_front_to_target += 2 * math.pi
        if angle_front_to_target > math.pi:
            angle_front_to_target -= 2 * math.pi

        if angle_front_to_target < math.radians(-10):
            # If the target is more than 10 degrees right from the centre, steer left
            self.controller.steer = -1
        elif angle_front_to_target > math.radians(10):
            # If the target is more than 10 degrees left from the centre, steer right
            self.controller.steer = 1
        else:
            # If the target is less than 10 degrees from the centre, steer straight
            self.controller.steer = 0

        self.controller.handbrake = abs(math.degrees(angle_front_to_target)) < self.POWERSLIDE_ANGLE

    def check_for_dodge(self):
        if self.should_dodge and time.time() > self.next_dodge_time:
            self.controller.jump = True
            self.controller.pitch = -1

            if self.on_second_jump:
                self.on_second_jump = False
                self.should_dodge = False
            else:
                self.on_second_jump = True
                self.next_dodge_time = time.time() + self.DODGE_TIME

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        # Update game data variables
        self.bot_yaw = packet.game_cars[self.team].physics.rotation.yaw
        self.bot_pos = packet.game_cars[self.index].physics.location
        ball_pos = packet.game_ball.physics.location

        # Boost when ball is far enough away
        self.controller.boost = distance(self.bot_pos.x, self.bot_pos.y, ball_pos.x, ball_pos.y) > self.DISTANCE_FROM_BALL_TO_BOOST

        # Blue has their goal at -5000 (Y axis) and orange has their goal at 5000 (Y axis). This means that:
        # - Blue is behind the ball if the ball's Y axis is greater than blue's Y axis
        # - Orange is behind the ball if the ball's Y axis is smaller than orange's Y axis
        self.controller.throttle = 1

        self.time = packet.game_info.seconds_elapsed

        if self.will_be_goal(self.predict_path()) != (-1, -1):
            print('Goal in ' + str(self.will_be_goal(self.predict_path())[0] - self.time) + ' seconds')
            self.emergency()
        elif (self.index == 0 and self.bot_pos.y < ball_pos.y) or (self.index == 1 and self.bot_pos.y > ball_pos.y):
            self.aim(ball_pos.x, ball_pos.y)
            if distance(self.bot_pos.x, self.bot_pos.y, ball_pos.x, ball_pos.y) < self.DISTANCE_TO_DODGE:
                self.should_dodge = True
        else:
            if self.team == 0:
                # Blue team's goal is located at (0, -5000)
                self.aim(0, -5000)
            else:
                # Orange team's goal is located at (0, 5000)
                self.aim(0, 5000)

        # Boost on kickoff
        if ball_pos.x == 0 and ball_pos.x == 0:
            self.aim(ball_pos.x, ball_pos.x)
            self.controller.boost = True

        # This sets self.jump to be active for only 1 frame
        self.controller.jump = 0

        self.check_for_dodge()

        return self.controller


class Vector2:
    def __init__(self, x=0, y=0):
        self.x = float(x)
        self.y = float(y)

    def __add__(self, val):
        return Vector2(self.x + val.x, self.y + val.y)

    def __sub__(self, val):
        return Vector2(self.x - val.x, self.y - val.y)

    def correction_to(self, ideal):
        # The in-game axes are left handed, so use -x
        current_in_radians = math.atan2(self.y, -self.x)
        ideal_in_radians = math.atan2(ideal.y, -ideal.x)

        correction = ideal_in_radians - current_in_radians

        # Make sure we go the 'short way'
        if abs(correction) > math.pi:
            if correction < 0:
                correction += 2 * math.pi
            else:
                correction -= 2 * math.pi

        return correction


def get_car_facing_vector(car):
    pitch = float(car.physics.rotation.pitch)
    yaw = float(car.physics.rotation.yaw)

    facing_x = math.cos(pitch) * math.cos(yaw)
    facing_y = math.cos(pitch) * math.sin(yaw)

    return Vector2(facing_x, facing_y)

def draw_debug(renderer, car, ball, action_display):
    renderer.begin_rendering()
    # draw a line from the car to the ball
    renderer.draw_line_3d(car.physics.location, ball.physics.location, renderer.white())
    # print the action that the bot is taking
    renderer.draw_string_3d(car.physics.location, 2, 2, action_display, renderer.white())
    renderer.end_rendering()
