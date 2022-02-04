<template>
  <v-container grid-list-md>
    <v-layout wrap>
      <v-flex xs12>
        <span class="subtitle-2">Details</span>
      </v-flex>
      <v-flex xs12>
        <ValidationProvider name="Code" rules="required" immediate>
          <v-text-field
            v-model="code"
            slot-scope="{ errors, valid }"
            :error-messages="errors"
            :success="valid"
            label="Code"
            hint="Worker code as an unique key"
            clearable
            required
          />
        </ValidationProvider>
      </v-flex>

      <v-flex xs12>
        <team-select v-model="team" rules="required"></team-select>
      </v-flex>

      <v-flex xs12>
        <v-divider></v-divider>
        <span class="subtitle-2">Other Optional Information:</span>
        <v-divider></v-divider>
      </v-flex>

      <v-flex xs12>
        <location-select v-model="location" label="Home Location" rules="required"></location-select>
      </v-flex>

      <v-flex xs12>
        <login-username-select
          v-model="dispatch_user"
          label="login username"
          hint="The login-username"
          clearable
        ></login-username-select>
      </v-flex>

      <v-flex xs12>
        <v-text-field v-model="name" label="Name" hint="Name of worker." clearable />
      </v-flex>

      <v-flex xs12>
        <v-combobox
          v-model="skills"
          :items="team_requested_skills"
          label="skills"
          multiple
          chips
          clearable
          deletable-chips
        ></v-combobox>
      </v-flex>

      <InventoryCombobox
        v-model="loaded_items_conbobox"
        v-bind:items="select_inventory_copy"
        label="loaded items"
      />
      <v-flex xs12>
        <v-textarea
          v-model="description"
          label="Description"
          hint="Description of worker."
          clearable
        />
      </v-flex>
      <v-flex xs12>
        <v-switch
          v-model="is_active"
          hint="Whether the worker is active or not."
          label="is_active"
        />
      </v-flex>
    </v-layout>
  </v-container>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import TeamSelect from "@/team/TeamSelect.vue";
import LocationSelect from "@/location/LocationSelect.vue";
import InventoryCombobox from "@/item_inventory/InventoryCombobox.vue";
import { cloneDeep } from "lodash";
import { mapActions, mapMutations } from "vuex";
import LoginUsernameSelect from "../auth/LoginUsernameSelect.vue";
extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "WorkerNewEditSheet",

  components: {
    ValidationProvider,
    TeamSelect,
    LocationSelect,
    InventoryCombobox,
    LoginUsernameSelect,
  },
  data() {
    return {
      team_requested_skills: [],
    };
  },
  computed: {
    ...mapFields("worker", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.team",
      "selected.location",
      "selected.description",
      "selected.loading",
      "selected.flex_form_data",
      "selected.skills",
      "selected.loaded_items_conbobox",
      "selected.is_active",
      "selected.dispatch_user",
      "dialogs.showCreateEdit",
    ]),
    ...mapFields("item_inventory", ["select_inventory"]),
    select_inventory_copy: {
      get() {
        return cloneDeep(this.select_inventory);
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },
  methods: {
    ...mapMutations("worker", ["SET_ITEMS"]),
  },
  watch: {
    loaded_items_conbobox(newVal, oldVal) {
      if (newVal) {
        let request_item = newVal.reduce((pre, cur, index) => {
          return [...pre, cur.text];
        }, []);
        this.SET_ITEMS(request_item);
      }
    },
    team(newVal, oldVal) {
      if (newVal) {
        this.team_requested_skills =
          newVal.flex_form_data["requested_skills"] != undefined
            ? newVal.flex_form_data["requested_skills"]
            : [];
      }
    },
  },
};
</script>
