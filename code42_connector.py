# Python 3 Compatibility imports
from __future__ import print_function, unicode_literals

import json

import py42.sdk
import requests

# Phantom App imports
from py42.sdk.queries.alerts.alert_query import AlertQuery
from py42.sdk.queries.alerts.filters import Actor, AlertState, DateObserved

import phantom.app as phantom
from phantom.action_result import ActionResult
from phantom.base_connector import BaseConnector


class RetVal(tuple):

    def __new__(cls, val1, val2=None):
        return tuple.__new__(RetVal, (val1, val2))


class Code42Connector(BaseConnector):
    TEST_CONNECTIVITY_ACTION_ID = "test_connectivity"
    ADD_DEPARTING_EMPLOYEE_ACTION_ID = "add_departing_employee"
    REMOVE_DEPARTING_EMPLOYEE_ACTION_ID = "remove_departing_employee"
    GET_ALERT_DETAILS_ACTION_ID = "get_alert_details"
    SEARCH_ALERTS_ACTION_ID = "search_alerts"

    def __init__(self):
        super(Code42Connector, self).__init__()

        self._state = None
        self._cloud_instance = None
        self._username = None
        self._password = None
        self._client = None
        self._action_map = {
            self.TEST_CONNECTIVITY_ACTION_ID: lambda x: self._handle_test_connectivity(x),
            self.ADD_DEPARTING_EMPLOYEE_ACTION_ID: lambda x: self._handle_add_departing_employee(x),
            self.REMOVE_DEPARTING_EMPLOYEE_ACTION_ID: lambda x: self._handle_remove_departing_employee(x),
            self.GET_ALERT_DETAILS_ACTION_ID: lambda x: self._handle_get_alert_details(x),
            self.SEARCH_ALERTS_ACTION_ID: lambda x: self._handle_search_alerts(x)
        }

    @property
    def client(self):
        if self._client is None:
            self._client = py42.sdk.from_local_account(
                self._cloud_instance, self._username, self._password
            )
        return self._client

    def initialize(self):
        # Load the state in initialize, use it to store data
        # that needs to be accessed across actions
        self._state = self.load_state()

        # get the asset config
        config = self.get_config()
        self._cloud_instance = config["cloud_instance"]
        self._username = config["username"]
        self._password = config["password"]

        return phantom.APP_SUCCESS

    def handle_action(self, param):
        action_id = self.get_action_identifier()
        self.debug_print("action_id", action_id)
        action = self._action_map[action_id]
        return action(param)

    def _handle_test_connectivity(self, param):
        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))
        self.save_progress("Connecting to endpoint")

        try:
            # TODO
            # Ideally the client instantiation would happen in `initialize()` but that function does not have access
            # to the action, so it cannot effectively report errors to the UI.
            # Fix this with a decorator or something similar.
            self.client.users.get_current()
        except Exception as exception:
            return action_result.set_status(phantom.APP_ERROR, f"Unable to connect to Code42: {str(exception)}")

        self.save_progress("Test Connectivity Passed")
        return action_result.set_status(phantom.APP_SUCCESS)

    def _handle_add_departing_employee(self, param):
        self._log_action_handler()
        action_result = self._add_action_result(param)
        username = param["username"]
        departure_date = param.get("departure_date")
        user_id = self._get_user_id(username)
        response = self.client.detectionlists.departing_employee.add(user_id, departure_date=departure_date)

        note = param.get("note")
        if note:
            self.client.detectionlists.update_user_notes(user_id, note)

        action_result.add_data(response.data)
        action_result.update_summary({"user_id": user_id, "username": username})
        status_message = f"{username} was added to the departing employee list"
        return action_result.set_status(phantom.APP_SUCCESS, status_message)

    def _handle_remove_departing_employee(self, param):
        self._log_action_handler()
        action_result = self._add_action_result(param)
        username = param["username"]
        user_id = self._get_user_id(username)
        response = self.client.detectionlists.departing_employee.remove(user_id)
        action_result.add_data(response.data)
        action_result.update_summary({"user_id": user_id, "username": username})
        status_message = f"{username} was removed from the departing employee list"
        return action_result.set_status(phantom.APP_SUCCESS, status_message)

    def _handle_get_alert_details(self, param):
        self.save_progress(f"In action handler for: {self.get_action_identifier()}")
        action_result = self.add_action_result(ActionResult(dict(param)))
        alert_id = param["alert_id"]
        response = self.client.alerts.get_details([alert_id])
        alert = response.data["alerts"][0]
        action_result.add_data(alert)
        action_result.update_summary({"username": alert["actor"], "user_id": alert["actorId"]})
        return action_result.set_status(phantom.APP_SUCCESS)

    def _handle_search_alerts(self, param):
        self.save_progress(f"In action handler for: {self.get_action_identifier()}")
        action_result = self.add_action_result(ActionResult(dict(param)))
        username = param.get("username")
        start_date = param.get("start_date")
        end_date = param.get("end_date")
        alert_state = param.get("alert_state")

        if username is None and start_date is None and end_date is None and alert_state is None:
            return action_result.set_status(phantom.APP_ERROR, "Must supply a search term.")

        if not self._validate_date_range(start_date, end_date):
            return action_result.set_status(phantom.APP_ERROR, "Start Date and End Date are both required to search by "
                                                               "date range.")
        try:
            query = self._build_alerts_query(username, start_date, end_date, alert_state)
        except ValueError as exception:
            return action_result.set_status(phantom.APP_ERROR, f"Start Date and End Date must be in format YYYY-mm-dd: {exception}")

        response = self.client.alerts.search(query)
        action_result.add_data(response.data)
        return action_result.set_status(phantom.APP_SUCCESS)

    def finalize(self):
        # Save the state, this data is saved across actions and app upgrades
        self.save_state(self._state)
        return phantom.APP_SUCCESS

    def _validate_date_range(self, start_date, end_date):
        # Should we worry about whitespace param values?
        return (not start_date and not end_date) or (start_date is not None and end_date is not None)

    def _build_alerts_query(self, username, start_date, end_date, alert_status):
        filters = []
        if username is not None:
            filters.append(Actor.eq(username))
        if start_date is not None and end_date is not None:
            # This will raise a ValueError if dates not in Y-m-d H:M:S format
            filters.append(DateObserved.in_range(f"{start_date} 00:00:00", f"{end_date} 00:00:00"))
        if alert_status is not None:
            filters.append(self._build_alert_state_filter(alert_status))
        query = AlertQuery.all(*filters)
        return query

    def _build_alert_state_filter(self, alert_status):
        return AlertState.eq(AlertState.OPEN)

    def _get_user_id(self, username):
        users = self.client.users.get_by_username(username)["users"]
        if not users:
            raise Exception(f"User '{username}' does not exist")
        return users[0]["userUid"]

    def _log_action_handler(self):
        self.save_progress(f"In action handler for: {self.get_action_identifier()}")

    def _add_action_result(self, param):
        return self.add_action_result(ActionResult(dict(param)))


def main():
    import pudb
    import argparse

    pudb.set_trace()

    argparser = argparse.ArgumentParser()

    argparser.add_argument("input_test_json", help="Input Test JSON file")
    argparser.add_argument("-u", "--username", help="username", required=False)
    argparser.add_argument("-p", "--password", help="password", required=False)

    args = argparser.parse_args()
    session_id = None

    username = args.username
    password = args.password

    if username is not None and password is None:

        # User specified a username but not a password, so ask
        import getpass
        password = getpass.getpass("Password: ")

    csrftoken = None
    headers = None
    if username and password:
        try:
            login_url = Code42Connector._get_phantom_base_url() + "/login"

            print("Accessing the Login page")
            r = requests.get(login_url, verify=False)
            csrftoken = r.cookies["csrftoken"]

            data = dict()
            data["username"] = username
            data["password"] = password
            data["csrfmiddlewaretoken"] = csrftoken

            headers = dict()
            headers["Cookie"] = "csrftoken=" + csrftoken
            headers["Referer"] = login_url

            print("Logging into Platform to get the session id")
            r2 = requests.post(login_url, verify=False, data=data, headers=headers)
            session_id = r2.cookies["sessionid"]
        except Exception as e:
            print("Unable to get session id from the platform. Error: " + str(e))
            exit(1)

    with open(args.input_test_json) as f:
        in_json = f.read()
        in_json = json.loads(in_json)
        print(json.dumps(in_json, indent=4))

        connector = Code42Connector()
        connector.print_progress_message = True

        if session_id is not None:
            in_json["user_session_token"] = session_id
            if csrftoken and headers:
                connector._set_csrf_info(csrftoken, headers["Referer"])

        json_string = json.dumps(in_json)
        ret_val = connector._handle_action(json_string, None)
        print(json.dumps(json.loads(ret_val), indent=4))

    exit(0)


if __name__ == "__main__":
    main()
