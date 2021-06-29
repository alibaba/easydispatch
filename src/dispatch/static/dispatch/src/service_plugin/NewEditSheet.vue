<template>
  <v-navigation-drawer v-model="showCreateEdit" app clipped right width="500">
    <template v-slot:prepend>
      <v-list-item two-line>
        <v-list-item-content>
          <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
          <v-list-item-title v-else class="title">New</v-list-item-title>
          <v-list-item-subtitle>Plugins in Each Service</v-list-item-subtitle>
        </v-list-item-content>
        <v-btn icon color="primary" :loading="loading" @click="save()">
          <v-icon>save</v-icon>
        </v-btn>
        <v-btn icon color="secondary" @click="closeCreateEdit()">
          <v-icon>close</v-icon>
        </v-btn>
      </v-list-item>
    </template>
    <v-card flat>
      <v-card-text>
        <v-container grid-list-md>
          <v-layout wrap>
            <v-flex xs12>
              <service-select v-model="service" />
            </v-flex>
            <v-flex xs12>
              <v-select
                v-model="planning_plugin_type"
                label="Plugin Type"
                :items="planning_plugin_types_list"
                hint="Please choose a plugin type. This determines its behaviour"
                clearable
              />
            </v-flex>
            <v-flex xs12>
              <PluginCombobox
                v-model="plugin"
                label="Plugin Slug"
                hint="Please chooase a plugin by searching/selecting the slug."
              />
            </v-flex>
          </v-layout>
        </v-container>
      </v-card-text>
    </v-card>
  </v-navigation-drawer>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import ServiceSelect from "@/service_plugin/ServiceSelect.vue";
import PluginCombobox from "@/plugin/PluginCombobox.vue";

export default {
  name: "JobTypeNewEditSheet",

  components: {
    ServiceSelect,
    PluginCombobox,
  },

  data() {
    return {
      planning_plugin_types_list: [
        "kandbox_env_proxy",
        "kandbox_batch_optimizer",
        "kandbox_env",
        "kandbox_agent",
        "kandbox_rule",
        "kandbox_travel_time",
        "kandbox_data_adapter",
        "kandbox_data_generator",
      ],
      fake_text: "fake txt",
    };
  },

  computed: {
    ...mapFields("service_plugin", [
      "dialogs.showCreateEdit",
      "selected.plugin",
      "selected.service",
      "selected.config",
      "selected.planning_plugin_type",
      "selected.id",
      "selected.loading",
    ]),
  },

  methods: {
    ...mapActions("service_plugin", ["save", "closeCreateEdit"]),
    updatePluginMetadata(event) {
      this.plugin_metadata = event.data;
    },
  },
};
</script>
