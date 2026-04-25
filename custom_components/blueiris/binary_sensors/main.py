from __future__ import annotations

import json
import logging

from custom_components.blueiris.models.base_entity import BlueIrisEntity
from homeassistant.components.binary_sensor import STATE_ON, BinarySensorEntity
from homeassistant.components.mqtt import ReceiveMessage, async_subscribe
from homeassistant.core import callback

from ..helpers.const import *

_LOGGER = logging.getLogger(__name__)

CURRENT_DOMAIN = DOMAIN_BINARY_SENSOR


class BlueIrisMainBinarySensor(BinarySensorEntity, BlueIrisEntity):
    """Representation a binary sensor that is updated by MQTT."""

    remove_subscription = None

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.entity.state

    @property
    def device_class(self) -> BinarySensorDeviceClass | str | None:
        """Return the class of this sensor."""
        return self.entity.binary_sensor_device_class

    @property
    def force_update(self):
        """Force update."""
        return DEFAULT_FORCE_UPDATE

    async def async_added_to_hass_local(self):
        """Subscribe MQTT events."""
        _LOGGER.debug(f"Added new {self.name}")
        _LOGGER.debug(
            f"Subscribing to MQTT topics '{MQTT_ALL_TOPIC}', QOS: {DEFAULT_QOS}"
        )

        @callback
        def state_message_received(message: ReceiveMessage):
            """Handle a new received MQTT state message."""
            _LOGGER.debug(
                f"Received BlueIris Message - {message.topic}: {message.payload}"
            )

            self._state_message_received(message)

        self.remove_subscription = await async_subscribe(
            self.hass, MQTT_ALL_TOPIC, state_message_received, DEFAULT_QOS
        )

    async def async_will_remove_from_hass_local(self):
        if self.remove_subscription is not None:
            self.remove_subscription()
            self.remove_subscription = None

    def _state_message_received(self, message: ReceiveMessage):
        topic = message.topic
        raw_payload = message.payload

        _LOGGER.debug(f"[MQTT DEBUG] ── Incoming message ──────────────────────────")
        _LOGGER.debug(f"[MQTT DEBUG] Topic   : {topic}")
        _LOGGER.debug(f"[MQTT DEBUG] Payload : {raw_payload}")

        try:
            payload = json.loads(raw_payload)
        except Exception as parse_ex:
            _LOGGER.error(f"[MQTT DEBUG] Failed to parse JSON payload: {raw_payload!r} | Error: {parse_ex}")
            return

        raw_event_type = payload.get(MQTT_MESSAGE_TYPE, MQTT_MESSAGE_VALUE_UNKNOWN)
        trigger = payload.get(MQTT_MESSAGE_TRIGGER, MQTT_MESSAGE_VALUE_UNKNOWN).lower()

        _LOGGER.debug(f"[MQTT DEBUG] Extracted type    : {raw_event_type!r}")
        _LOGGER.debug(f"[MQTT DEBUG] Extracted trigger : {trigger!r}")

        event_type = raw_event_type.lower()

        if SENSOR_MOTION_NAME.lower() in event_type:
            _LOGGER.debug(f"[MQTT DEBUG] Normalising event_type '{event_type}' → '{SENSOR_MOTION_NAME.lower()}'")
            event_type = SENSOR_MOTION_NAME.lower()

        value = trigger == STATE_ON

        _LOGGER.debug(f"[MQTT DEBUG] Resolved event_type : {event_type!r}")
        _LOGGER.debug(f"[MQTT DEBUG] Resolved value      : {value}  (trigger '{trigger}' == '{STATE_ON}')")

        # Show the exact key that will be written to mqtt_states
        expected_key = f"{topic}_{event_type}".lower()
        _LOGGER.debug(f"[MQTT DEBUG] mqtt_states key     : {expected_key!r}")

        # Show all currently registered sensor topics so we can spot mismatches
        registered_topics = set()
        for domain_entities in self.entity_manager.entities.values():
            for ent in domain_entities.values():
                if hasattr(ent, "topic") and ent.topic:
                    registered_topics.add(ent.topic.lower())
        _LOGGER.debug(f"[MQTT DEBUG] Registered topics   : {sorted(registered_topics)}")

        if topic.lower() not in registered_topics:
            _LOGGER.warning(
                f"[MQTT DEBUG] ⚠ Topic '{topic}' does NOT match any registered entity topic! "
                f"State update will be stored but no entity will consume it."
            )

        self.entity_manager.set_mqtt_state(topic, event_type, value)

        _LOGGER.debug(f"[MQTT DEBUG] mqtt_states after set: { {k: v for k, v in self.entity_manager.mqtt_states.items()} }")

        self.entity_manager.update()

        self.hass.async_create_task(self.ha.dispatch_all())
        _LOGGER.debug(f"[MQTT DEBUG] ── dispatch_all fired ─────────────────────────")

    def _immediate_update(self, previous_state: bool):
        if previous_state != self.entity.state:
            _LOGGER.debug(
                f"{self.name} updated from {previous_state} to {self.entity.state}"
            )

        super()._immediate_update(previous_state)
