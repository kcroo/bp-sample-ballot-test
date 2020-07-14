import psycopg2
import os
import threading
from collections import Counter
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# locating elements in web page: https://selenium-python.readthedocs.io/locating-elements.html
# radio buttons example: http://allselenium.info/working-with-radiobuttons-using-python-selenium-webdriver/
# creating geodataframe from list of tuple coordinates using geoseries: https://gis.stackexchange.com/questions/266098/how-to-convert-a-geoserie-to-a-geodataframe-with-geopandas
# creating shapely Points from coordinate tuple: https://shapely.readthedocs.io/en/latest/manual.html#points

class SampleBallotThread (threading.Thread):
    def __init__(self, driver_options, district, date, coords, results):
        threading.Thread.__init__(self)

        self.district = district
        self.election_date = date
        self.coords = coords
        self.results = results
        self.URL = 'https://ballotpedia.org/Sample_Ballot_Lookup'

        exe_path = os.environ.get('CHROMEDRIVER_PATH')
        if exe_path == None:
            exe_path = './chromedriver.exe'
            print('error with exe_path - using local') 
            
        self.driver = webdriver.Chrome(executable_path=exe_path, options=driver_options)
        

    def run(self):
        latitude = self.coords[1]
        longitude = self.coords[0]

        try:
            self.driver.get(self.URL)

            ### input address
            addressInput = self.driver.find_element_by_id('bp-sbl-address-input')
            addressInput.clear()
            addressInput.send_keys(f'{latitude} {longitude}', Keys.RETURN)

            ### select election date (if no dates, will proceed to sample ballot)
            if self.election_date != None:
                electionButton = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, f'//input[@value="{self.election_date}"]'))
                )
                electionButton.click()
            else:
                electionButton = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, 'election'))
                )
                electionButton.click()
            
            # set wait time for ALL subsequent find operations with selenium
            self.driver.implicitly_wait(5)
            
            # find continue button and click it -> brings it to sample ballot results
            continueButton = self.driver.find_element_by_class_name('bp-sbl-choose-continue')
            continueButton.click()

            ### sample ballot results
            # get text of all districts and see if district name is in results
            districts = self.driver.find_element_by_id('bp-sbl-districts').text

            if self.district['name'] in districts:
                self.results['in_results'].append([latitude, longitude])
            else:
                self.results['not_in_results'].append([latitude, longitude])

            # get text of all candidates: add to has_candidates if found; otherwise add to no_candidates
            found_candidates = False
            candidates_elements = self.driver.find_elements_by_css_selector('#bp-sbl-results-district-undefined > div.bp-sbl-results-district-title.bp-sbl-active.bp-sbl > h3')
        
            for x in candidates_elements:
                if self.district['name'] in x.text:
                    self.results['has_candidates'].append([latitude, longitude])
                    found_candidates = True
                    break
            
            # if no candidates found, add to no_candidates list
            if found_candidates == False:
                self.results['no_candidates'].append([latitude, longitude])

            # get text of all district types (find_elements returns list of selenium elements)
            district_types_elements = self.driver.find_elements_by_class_name('bp-sbl-district-type')
            types_text = [x.text for x in district_types_elements]

            # count how many of each district type there are (typically should only have one of each -> if more, add to results)
            # key is type name, value is how many of that type
            count_district_types = Counter(types_text)

            for key, value in count_district_types.items():
                if key != '' and value > 1:
                    self.results['multiple_districts_of_same_type'].append(((latitude, longitude), key))

            # save page URL to results
            self.results['links'].append(self.driver.current_url)

        # occurs for explicit wait (election button); if it can't be found in 10 seconds -> stop current point's test
        except TimeoutException:
            print('Timed out')
            self.results['errors'].append((latitude, longitude))

        # occurs if implicit wait button can't be found -> stop current point's test
        except NoSuchElementException:
            print('Couldn\'t find element')
            self.results['errors'].append((latitude, longitude))

        # occurs if no election list, because there's only one upcoming election -> keep going with test
        except ElementNotInteractableException:
            pass

        finally:
            self.driver.quit()

            
class SampleBallotTest:
    def __init__(self, district_id, election_date, number_of_points, app_config):
        try:
            self.district_id = int(district_id)

            # input validation for date and number of points done in web form
            if election_date == '':
                self.election_date = None
            else:
                self.election_date = election_date 

            if number_of_points == '': 
                self.number_of_points = 3
            else:      
                self.number_of_points = int(number_of_points)

            # connect to database
            self.connection = psycopg2.connect(user = app_config['DB_USER'],
                                        password = app_config['DB_PASSWORD'],
                                        host = app_config['DB_HOST'],
                                        dbname = app_config['DB_NAME'])

            self.cursor = self.connection.cursor()
        
        except (Exception, psycopg2.Error) as error:
            print(f'An error occurred connecting to the database: {error}')

    def get_district_boundary_and_points(self):
        try:
            # query: district name, district type, multipoint text of random points
            query_name_type_boundary_random_points = """
                SELECT districts.name, districts.type, ST_AsGeoJSON(boundary), ST_AsText(ST_GeneratePoints(district_boundaries.boundary::geometry, %s))
                FROM district_boundaries
                INNER JOIN districts ON district_boundaries.district = districts.id
                WHERE district = %s;
            """
            self.cursor.execute(query_name_type_boundary_random_points, (self.number_of_points, self.district_id))
            result = self.cursor.fetchone()
            self.cursor.close()
			#self.connection.close()
            
			# save database results
            self.district_name = result[0]
            self.district_type = result[1]
            self.district_boundary = result[2]
            random_points = result[3]

            # points are in "MULTIPOINT(-94.4494114292083 39.3751889719326,-94.3134791977004 39.3551582995212)" format
            # leave off MULTIPOINT() and add tuple of coordinate pairs to list of points
            self.random_points_geometry = []
            for coord in random_points[11:-1].split(','):
                longitude, space, latitude = coord.partition(' ')
                self.random_points_geometry.append((longitude, latitude))
   
            print(self.random_points_geometry)

            # set up options for web browser (Chrome)
            self.driver_options = webdriver.ChromeOptions()
            self.driver_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
            self.driver_options.add_argument('--headless')
            self.driver_options.add_argument('--no-sandbox')
            self.driver_options.add_argument('--disable-dev-shm-usage')

        except (Exception, psycopg2.Error) as error:
            print(f'An error occurred while getting district boundary and random points: {error}')


    def run_chrome_tests(self):
        try:
            # dictionary to hold district information 
            district = {
                'ID': self.district_id,
                'name': self.district_name,
                'type': self.district_type,
            }

            # dictionary of arrays to hold results (easier to pass dictionary to the threads)
            results = {
                'in_results': [],
                'not_in_results': [],
                'has_candidates': [],
                'no_candidates': [],
                'errors': [],
                'multiple_districts_of_same_type': [],
                'links': [],
                'district_boundary': self.district_boundary,
                'random_points': self.random_points_geometry
            }

            threads = []

            # create thread for each random point to put through sample ballot lookup
            for coords in self.random_points_geometry:
                thread = SampleBallotThread(self.driver_options, district, self.election_date, coords, results)
                # start() invokes run method in SampleBallotThread class
                thread.start()
                threads.append(thread)

            # wait for all threads to finish
            for thread in threads:
                thread.join()

            # TODO: remove after done debugging - prints results after loop is done
            if self.election_date != None:
                print(f'RESULTS FOR {self.election_date}')
            else:
                print(f'RESULTS')

            print(f'In results: {results["in_results"]}')
            print(f'Not in results: {results["not_in_results"]}')
            print(f'Has candidates: {results["has_candidates"]}')
            print(f'Does not have candidates: {results["no_candidates"]}')
            print(f'Has multiple districts of same type: {results["multiple_districts_of_same_type"]}')
            print(f'Links to sample ballot:')
            [print(x) for x in results['links']]

            return results

        except (Exception, psycopg2.Error) as error:
            print(f'An error occurred: {error}')

    def run(self):
        self.get_district_boundary_and_points()
        results = self.run_chrome_tests()
        return results
