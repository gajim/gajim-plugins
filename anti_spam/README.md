# Anti_spam Plugin for Gajim

This Plugin allows you to dissociate itself from the spam.

## Installation

Use special plugin, that manages automatic download and installation of others plugins, it is called Plugin Installer.

## Options
### Block pubsub

Block incoming messages from pubsub

### Message size limit

Block incoming messages that have size more than configured. Default value -1 mean that any sized messages are coming.

### Anti spam question

Block incoming messages from users not in your roster. In response, the Plugin sends a question that you configured. After correct answer(also configurable) you will receive all new messages from user.
**Attention!** All messages before correct answer will be lost.
Also you can enable this function, in Plugin config, for conference private messages. In some servers, the question in conference private does not reach your interlocutor. This can lead to the fact that you will not receive any messages from him, and he will not know it.