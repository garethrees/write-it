# -*- coding: utf-8 -*-
from tastypie.resources import ModelResource, ALL_WITH_RELATIONS, Resource
from nuntium.models import WriteItInstance, Message, Answer, OutboundMessageIdentifier, OutboundMessage
from tastypie.authentication import ApiKeyAuthentication, Authentication
from tastypie.authorization import Authorization
from django.core.exceptions import ObjectDoesNotExist
from django.conf.urls import url
from tastypie import fields
from tastypie.exceptions import ImmediateHttpResponse
from tastypie import http
from django.http import HttpRequest
from popit.models import Person
from contactos.models import Contact

class PersonResource(ModelResource):
    class Meta:
        queryset = Person.objects.all()
        resource_name = 'person'
        authentication = ApiKeyAuthentication()

    def dehydrate(self, bundle):
        bundle.data['resource_uri'] = bundle.obj.popit_url
        return bundle

class WriteItInstanceResource(ModelResource):
    # I should add persons but the thing is that it breaks some other tests and I'm running out of time
    # so now you cannot create a writeit instance with persons just with a popit-instance =) 
    # regards the lazy programmer
    class Meta:
        queryset = WriteItInstance.objects.all()
        resource_name = 'instance'
        authorization = Authorization()
        authentication = ApiKeyAuthentication() 
        always_return_data = True

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<id>[-\d]+)/messages/$" % self._meta.resource_name, self.wrap_view('handle_instance_messages'), name="api_handle_messages"),
        ]

    def handle_instance_messages(self,request, *args, **kwargs):
        basic_bundle = self.build_bundle(request=request)
        obj = self.cached_obj_get(bundle=basic_bundle, **self.remove_api_resource_names(kwargs))
        resource = MessageResource()
        return resource.get_list(request, writeitinstance=obj)


    def dehydrate(self, bundle):
        #not completely sure that this is the right way to get the messages
        bundle.data['messages_uri'] = bundle.data['resource_uri']+'messages/'
        bundle.data['persons'] = []
        for person in bundle.obj.persons.all():
            bundle.data['persons'].append(person.popit_url)
        return bundle

    def hydrate(self, bundle):
        bundle.obj.owner = bundle.request.user
        return bundle

    def obj_create(self, bundle):
        bundle = super(WriteItInstanceResource, self).obj_create(bundle)
        instance = bundle.obj
        if "popit-api" in bundle.data and bundle.data["popit-api"]:
            instance.load_persons_from_a_popit_api(bundle.data["popit-api"])
        return bundle

class AnswerResource(ModelResource):
    class Meta:
        queryset =  Answer.objects.all()
        resource_name = 'answer'

class MessageResource(ModelResource):
    writeitinstance = fields.ToOneField(WriteItInstanceResource, 'writeitinstance')
    answers = fields.ToManyField(AnswerResource, 'answers', null=True, full=True)

    class Meta:
        queryset = Message.objects.all()
        resource_name = 'message'
        authorization = Authorization()
        authentication = ApiKeyAuthentication()
        always_return_data = True
        filtering = {
            'writeitinstance': ALL_WITH_RELATIONS
        }

    def hydrate(self, bundle):
        persons = []
        if bundle.data['persons'] == 'all':
            instance = WriteItInstanceResource().get_via_uri(bundle.data["writeitinstance"])
            for person in instance.persons.all():
                persons.append(person)
        else:
            for popit_url in bundle.data['persons']:
                try:
                    person = Person.objects.get(popit_url=popit_url)
                    persons.append(person)
                except ObjectDoesNotExist:
                    pass
        bundle.obj.persons = persons
        bundle.obj.confirmated = True
        return bundle

    def obj_create(self, bundle, **kwargs):
        bundle = super(MessageResource, self).obj_create(bundle, **kwargs)
        bundle.obj.recently_confirmated()
        return bundle


class AnswerCreationResource(Resource):
    class Meta:
        resource_name = 'create_answer'
        object_class = Answer
        authentication = ApiKeyAuthentication()
        allowed_methods = ['post', ]


    def obj_create(self, bundle, **kwargs):
        identifier_key = bundle.data['key']
        identifier = OutboundMessageIdentifier.objects.get(key=bundle.data['key'])
        owner = identifier.outbound_message.message.writeitinstance.owner
        
        if owner!=bundle.request.user:
            raise ImmediateHttpResponse(response=http.HttpUnauthorized())

        answer_content = bundle.data['content']
        OutboundMessageIdentifier.create_answer(identifier_key, answer_content)


class HandleBouncesResource(Resource):
    class Meta:
        resource_name = 'handle_bounce'
        object_class = Contact
        authentication = ApiKeyAuthentication()
        allowed_methods = ['post', ]


    def obj_create(self, bundle, **kwargs):
        identifier_key = bundle.data['key']
        identifier = OutboundMessageIdentifier.objects.get(key=bundle.data['key'])
        outbound_message = OutboundMessage.objects.get(outboundmessageidentifier=identifier)
        contact = outbound_message.contact
        contact.is_bounced = True
        contact.save()