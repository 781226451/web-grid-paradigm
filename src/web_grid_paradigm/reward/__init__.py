"""Reward subsystem — two independent modules.

``policy``  *when* to reward: ``per_hit`` (default), ``ratio`` (FR-n), ``none``.
``sink``    *how* to reward: ``serial`` (default, Arduino), ``test`` (dry run),
            ``off``.

They share no code: ``policy`` only produces a decision, ``sink`` only sends
one, so either side can be replaced without touching the other.  They are
combined in exactly one place, ``web_grid_paradigm.app.runner`` /
``reporter``.  Import the modules directly::

    from web_grid_paradigm.reward.policy import build_reward_policy
    from web_grid_paradigm.reward.sink import build_reward_sink
"""
