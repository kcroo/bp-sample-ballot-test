from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField, SelectField, HiddenField
from wtforms.widgets.html5 import NumberInput
from wtforms.widgets import HiddenInput
from wtforms.fields.html5 import DateField
from wtforms.validators import DataRequired, Length, NumberRange, ValidationError, AnyOf, Optional, Email
from datetime import date, timedelta

class NewTest(FlaskForm):
    district_id = IntegerField('District ID', widget=NumberInput(), validators=[DataRequired(), NumberRange(min=1)])
    election_date = DateField('Election Date (Optional)', validators=[Optional()])
    number_of_points = IntegerField('Number of Random Points (Optional)', widget=NumberInput(), validators=[Optional(), NumberRange(min=1, max=5)])
    submit = SubmitField('Start Test')

    def validate_election_date(self, election_date):
        print(election_date.data, date.today())
        if election_date.data and election_date.data < date.today():
            raise ValidationError('Election date cannot be in the past.')
