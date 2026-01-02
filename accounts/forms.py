from django import forms


class EmailLoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


class OtpVerifyForm(forms.Form):
    code = forms.CharField(min_length=4, max_length=10)
