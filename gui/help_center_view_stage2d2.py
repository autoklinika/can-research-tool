from __future__ import annotations

from app import help_catalog_registry as registry

from . import help_center_view as _base


# Keep the established widget implementation while replacing its module-level
# catalog bindings with the feature registry. This lets future stages add Help
# topics without editing the large Stage 1 catalog in place.
_base.HELP_CATEGORY_ORDER = registry.HELP_CATEGORY_ORDER
_base.HELP_TOPICS = registry.HELP_TOPICS
_base.HelpTopic = registry.HelpTopic
_base.help_topic = registry.help_topic
_base.render_help_home_html = registry.render_help_home_html
_base.render_help_topic_html = registry.render_help_topic_html
_base.search_help_topics = registry.search_help_topics

HelpCenterWidget = _base.HelpCenterWidget


__all__ = ["HelpCenterWidget"]
