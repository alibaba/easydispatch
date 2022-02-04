<template>
  <ValidationObserver>
    <v-navigation-drawer v-model="showCreateEdit" app clipped right width="500">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
            <v-list-item-title v-else class="title">New</v-list-item-title>
            <v-list-item-subtitle>Location</v-list-item-subtitle>
          </v-list-item-content>
          <v-btn
            icon
            color="primary"
            :loading="loading" 
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
                <ValidationProvider name="location_code" rules="required" immediate>
                  <v-text-field
                    v-model="location_code"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="location_code"
                    hint="A name for your   location."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>
              <v-flex xs12>
                <team-select v-show=" 'Customer' != userInfo.role " v-model="team" rules="required"></team-select>
              </v-flex>
              
              <v-flex xs12>
                <ValidationProvider name="geo_address_text" rules="required" immediate>
                  <v-textarea
                    v-model="geo_address_text"
                    slot-scope="{ errors, valid }"
                    label="Address in Plain Text"
                    :error-messages="errors"
                    :success="valid"
                    hint="A description for your location."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>

              <v-flex xs6>
                <ValidationProvider name="geo_longitude" rules="required" immediate>
                  <v-text-field
                    v-model="geo_longitude"
                    type="number"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="geo_longitude"
                    hint="x, or longitude."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>
              <v-flex xs6>
                <ValidationProvider name="geo_latitude" rules="required" immediate>
                  <v-text-field
                    v-model="geo_latitude"
                    type="number"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="geo_latitude"
                    hint="y, or geo_latitude."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>

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
import { mapState } from "vuex";

import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import TeamSelect from "@/team/TeamSelect.vue";

extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "LocationNewEditSheet",

  components: {
    ValidationObserver,
    ValidationProvider,
    TeamSelect,
  },

  data() {
    return {};
  },
  computed: {
    ...mapState("auth", ["userInfo"]),
    ...mapFields("location", [
      "dialogs.showCreateEdit",
      "selected.loading",
      "selected.id",
      "selected.location_code",
      "selected.geo_longitude",
      "selected.geo_latitude",
      "selected.geo_address_text",
      "selected.geo_json",
      "selected.team",
    ]),
  },

  methods: {
    ...mapActions("location", ["save", "closeCreateEdit"]),
  },
};
</script>
