<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-navigation-drawer v-model="showCreateEdit" app clipped right width="500">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
            <v-list-item-title v-else class="title">New</v-list-item-title>
            <v-list-item-subtitle>Service</v-list-item-subtitle>
          </v-list-item-content>
          <v-btn
            icon
            color="primary"
            :loading="loading"
            :disabled="invalid || !validated"
            @click="save()"
          >
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
                <span class="subtitle-2">Details</span>
              </v-flex>
              <v-flex xs12>
                <ValidationProvider name="ServiceCode" rules="required" immediate>
                  <v-text-field
                    v-model="code"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Service Code"
                    hint="A code for your planner service."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>
              <v-flex xs12>
                <ValidationProvider name="ServiceName" rules="required" immediate>
                  <v-text-field
                    v-model="name"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Service Name"
                    hint="Name for your planner service."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>
              <v-flex xs12>
                <v-textarea
                  v-model="description"
                  label="Description"
                  hint="A description for your service."
                  clearable
                />
              </v-flex>
              <!-- Disable type (default to pager duty) until we have a way to validate. -->

              <!-- <v-flex xs12>
                <v-switch
                  v-model="is_active"
                  :label="is_active ? 'Active' : 'Inactive'"
                />
              </v-flex>-->
            </v-layout>
          </v-container>
        </v-card-text>
      </v-card>
    </v-navigation-drawer>
  </ValidationObserver>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import PluginApi from "@/plugin/api";

extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "ServiceNewEditSheet",

  components: {
    ValidationObserver,
    ValidationProvider,
  },

  computed: {
    ...mapFields("service", [
      "selected.code",
      "selected.name",
      "selected.id",
      "selected.description",
      "selected.is_active",
      "selected.loading",
      "dialogs.showCreateEdit",
    ]),
  },

  methods: {
    ...mapActions("service", ["save", "closeCreateEdit"]),
  },

  data() {
    return {
      oncall_plugins: null,
    };
  },

  mounted() {
    this.loading = true;
    PluginApi.getByType("oncall").then((response) => {
      this.loading = false;
      this.oncall_plugins = response.data.items.map((p) => p.slug);
    });
  },
};
</script>
