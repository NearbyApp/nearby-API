#!/usr/bin/env python
import json
import urllib2
import datetime

from bson import ObjectId
from oauth2client import client, crypt

from app import mongo

class SpottedModel(object):

	@staticmethod
	def createSpotted(userId, anonymity, latitude, longitude, message, picture=None):
		"""Creates a spotted.
		"""
		if not picture is None:
			# Save it to S3, then keep the picture link to save it in the table.
			pass

		return mongo.db.spotteds.insert_one(
			{
				'userId': userId,
				'anonymity': anonymity,
				'archived': False,
				'location': {
					'type':'Point',
					'coordinates': [
						float(latitude), 
						float(longitude)
					]
				},
				'creationDate' : datetime.datetime.utcnow(),
				# Add picture link here
				'message': message
			}
		).inserted_id

	@staticmethod
	def getSpottedBySpottedId(spottedId):
		"""Gets a spotted by spottedId.
		"""
		return mongo.db.spotteds.find_one({'_id': ObjectId(spottedId), 'archived': False}, projection={'archived': False})

	@staticmethod
	def getSpotteds(minLat, minLong, maxLat, maxLong, locationOnly):
		"""Gets a list of spotteds by using the latitude, longitude and radius.
		locationOnly returns only get the location of the returned spotteds if true.
		"""
		projection = {}
		projection['_id'] = True
		projection['location'] = True

		if not locationOnly:
			projection['anonymity'] = True
			projection['archived'] = True
			projection['creationDate'] = True
			projection['message'] = True
			projection['userId'] = True

		return [spotted for spotted in mongo.db.spotteds.find(
				{
					'anonymity': False,
					'archived': False,
					'location': {
						'$geoWithin': {
							'$geometry': {
								'type': 'Polygon',
								'coordinates': [
									[
										[float(minLat), float(minLong)],
										[float(minLat), float(maxLong)],
										[float(maxLat), float(maxLong)],
										[float(maxLat), float(minLong)],
										[float(minLat), float(minLong)]
									]
								]
							}
						}
					}
				},
				projection=projection
			)
		]
		
	@staticmethod
	def getMySpotteds(userId):
		"""Gets a list of spotteds by using the userId of a specific user.
		"""
		return [x for x in mongo.db.spotteds.find({'userId': ObjectId(userId)}, projection={'archived': False})]

	@staticmethod
	def getSpottedsByUserId(userId):
		"""Gets a list of spotteds by using the userId of a specific user.
		"""
		res = [x for x in mongo.db.spotteds.find({'userId': ObjectId(userId), 'anonymity': False, 'archived': False}, projection={'archived': False})]
		return res

class UserModel(object):

	@staticmethod
	def createUser(facebookToken=None, googleToken=None):
		"""THIS METHOD SHOULDN'T BE USED ELSEWHERE THAN IN FacebookModel AND GoogleModel.
		Creates a user with either facebookToken or googleToken.
		"""
		facebookId = None
		googleId = None
		facebookDate = None
		googleDate = None
		fullName = None
		profilPictureURL = None

		if not facebookToken == None:
			facebookId = facebookToken['user_id']
			url = "https://graph.facebook.com/{facebookId}?fields=name,picture&access_token={accessToken}"
			res = urllib2.urlopen(url.format(facebookId=facebookId,accessToken=facebookToken['token']))
			data = json.loads(res.read())
			profilPictureURL = data['picture']['data']['url']
			fullName = data['name']
			facebookDate = datetime.datetime.utcnow()
		
		if not googleToken == None:
			googleId = googleToken['sub']
			profilPictureURL = googleToken['picture']
			fullName = googleToken['name']
			googleDate = datetime.datetime.utcnow()

		userId = False

		if facebookId or googleId:
			userId = mongo.db.users.insert_one(
				{
					'facebookId': facebookId,
					'googleId': googleId,
					'fullName': fullName,
					'profilPictureURL': profilPictureURL,
					'disabled': False,
					'creationDate' : datetime.datetime.utcnow(),
					'facebookDate' : facebookDate,
					'googleDate' : googleDate,
				}
			).inserted_id

		return userId

	@staticmethod
	def disableUser(userId):
		res = False
		if mongo.db.users.update_one({'_id': userId}, {'disabled': True}).modified_count == 1:
			mongo.db.spotteds.update_many({'userId': userId}, {'archived': True})
			res = True
		return res

	@staticmethod
	def doesUserExist(userId):
		"""Checks if a user exists by userId.
		"""
		return True if UserModel.getUser(userId) else False

	@staticmethod
	def enableUser(userId):
		res = False
		if mongo.db.users.update_one({'_id': userId}, {'disabled': False}).modified_count == 1:
			mongo.db.spotteds.update_many({'userId': userId}, {'archived': False})
			res = True
		return res

	@staticmethod
	def getUser(userId):
		"""Gets a user by userId.
		"""
		return mongo.db.users.find_one({'_id': ObjectId(userId)})

	@staticmethod
	def isDisabled(userId):
		res = True
		user = mongo.db.users.find_one({'_id': ObjectId(userId)})
		if user and not user.disabled:
			res = False

		return res

	@staticmethod
	def mergeUsers(userIdNew, userIdOld):
		res = False
		userOld = UserModel.getUser(userIdNew)
		userNew = UserModel.getUser(userIdOld)

		if userOld and userNew \
		and (not userOld['facebookId'] and userNew['facebookId'] and not userNew['googleId'] \
		or not userOld['googleId'] and userNew['googleId'] and not userNew['facebookId']):
			if not userOld['facebookId'] and userNew['facebookId']:
				if mongo.db.users.update_one({'_id': userIdNew}, {'facebookId': userNew['facebookId'], 'facebookDate': datetime.datetime.utcnow()}).modified_count == 1:
					res = True

			elif not userOld['googleId'] and userNew['googleId']:
				if mongo.db.users.update_one({'_id': userIdNew}, {'googleId': userNew['googleId'], 'googleDate': datetime.datetime.utcnow()}).modified_count == 1:
					res = True

			if res:
				mongo.db.spotteds.update_many({'userId': userIdOld}, {'userId': userIdNew})

		return res


class FacebookModel(UserModel):

	@staticmethod
	def createUserWithFacebook(facebookToken):
		"""Creates a user related to a facebookToken.
		"""
		if not FacebookModel.doesFacebookIdExist(facebookToken['user_id']):
			return UserModel.createUser(facebookToken=facebookToken)
		return False

	@staticmethod
	def doesFacebookIdExist(facebookId):
		"""Checks if a user exists by facebookId.
		"""
		return True if FacebookModel.getUserByFacebookId(facebookId) else False

	@staticmethod
	def getTokenValidation(accessToken, token):
		"""Calls Facebook to receive a validation of a Facebook user token.
		"""
		url = "https://graph.facebook.com/debug_token?input_token={input_token}&access_token={accessToken}"
		res = urllib2.urlopen(url.format(input_token=token, accessToken=accessToken))
		data = json.loads(res.read())['data']
		data['token'] = token
		return data

	@staticmethod
	def getUserByFacebookId(facebookId):
		"""Gets a user by facebookId.
		"""
		return mongo.db.users.find_one({'facebookId': facebookId})

	@staticmethod
	def registerFacebookIdToUserId(userId, facebookId):
		"""Register a Facebook account to a user.
		"""
		res = False
		if not FacebookModel.doesFacebookIdExist(facebookId):
			user = UserModel.getUser(userId)
			if user and FacebookModel.validateUserIdAndFacebookIdLink(userId, None):
				res = mongo.db.users.update_one({'_id': userId}, {'facebookId': facebookId}).modified_count == 1

		return res

	@staticmethod
	def validateUserIdAndFacebookIdLink(userId, facebookId):
		"""Validate the link between a user and a Facebook account.
		"""
		res = False
		user = UserModel.getUser(userId)
		if user and user['facebookId'] == facebookId:
			res = True

		return res

class GoogleModel(UserModel):

	@staticmethod
	def createUserWithGoogle(googleToken):
		"""Creates a user related to a googleToken.
		"""
		if not GoogleModel.doesGoogleIdExist(googleToken['sub']):
			return UserModel.createUser(googleToken=googleToken)
		return False

	@staticmethod
	def doesGoogleIdExist(googleId):
		"""Checks if a user exists by googleId.
		"""
		return True if GoogleModel.getUserByGoogleId(googleId) else False

	@staticmethod
	def getTokenValidation(clientId, token):
		"""Calls Google to receive a validation of a Google user token.
		"""
		tokenInfo = None
		try:
			tokenInfo = client.verify_id_token(token, clientId)

			if tokenInfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
				raise crypt.AppIdentityError("Wrong issuer.")

		except crypt.AppIdentityError as e:
			print(e)
			tokenInfo = False
		
		return tokenInfo

	@staticmethod
	def getUserByGoogleId(googleId):
		"""Gets a user by googleId.
		"""
		return mongo.db.users.find_one({'googleId': googleId})

	@staticmethod
	def registerGoogleIdToUserId(userId, googleId):
		"""Register a Google account to a user.
		"""
		res = False
		if not GoogleModel.doesGoogleIdExist(googleId):
			user = UserModel.getUser(userId)
			if user and GoogleModel.validateUserIdAndGoogleIdLink(userId, None):
				res = mongo.db.users.update_one({'_id': userId}, {'googleId': googleId}).modified_count == 1
		
		return res

	@staticmethod
	def validateUserIdAndGoogleIdLink(userId, googleId):
		"""Validate the link between a user and a Google account.
		"""
		res = False
		user = UserModel.getUser(userId)
		if user and user['googleId'] == googleId:
			res = True

		return res
